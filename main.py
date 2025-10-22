from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging
import requests

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# --- Updated: Allowed Qualities for Filtering ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]
# ---

class UniversalVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': False,
            'no_warnings': False,
        }
    
    def get_supported_sites(self):
        """Get list of all supported sites by yt-dlp"""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                return ydl.extractor._ies.keys()
        except:
            return []
    
    def validate_url(self, url):
        """Validate if URL is supported by yt-dlp"""
        if not url or not isinstance(url, str):
            return False
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # Try to extract info without downloading
                # process=False is safer for just checking validity
                ydl.extract_info(url, download=False, process=False)
                return True
        except:
            return False
    
    def get_video_info(self, url):
        """Get video information from any supported platform"""
        try:
            logger.info(f"Fetching info for: {url}")
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("Video not found or inaccessible")
                
                # Extract basic info
                video_data = {
                    'success': True,
                    'id': info.get('id', ''),
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self._format_duration(info.get('duration')),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'description': info.get('description', '')[:200] + '...' if info.get('description') else '',
                    'webpage_url': info.get('webpage_url', ''),
                    'extractor': info.get('extractor', 'Unknown Platform'),
                    'formats': []
                }
                
                # Process available formats
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        # --- Updated: Only keep formats that have both video and audio or are pure audio.
                        # We will use yt-dlp's internal merging for video+audio download.
                        is_video = fmt.get('vcodec') != 'none'
                        is_audio = fmt.get('acodec') != 'none'
                        
                        # Only show 'video with sound' formats or pure 'audio' formats in the list.
                        # For video, we will rely on a custom format string during download.
                        if is_video and is_audio:
                            format_info = {
                                'format_id': fmt.get('format_id', ''),
                                'ext': fmt.get('ext', 'mp4'),
                                'quality': self._get_quality_display(fmt),
                                'filesize': self._format_filesize(fmt.get('filesize')),
                                'format_note': fmt.get('format_note', ''),
                                'vcodec': fmt.get('vcodec', 'none'),
                                'acodec': fmt.get('acodec', 'none'),
                                'width': fmt.get('width'),
                                'height': fmt.get('height'),
                                'fps': fmt.get('fps'),
                                'type': 'video_with_audio'
                            }
                            formats.append(format_info)
                        elif is_audio and not is_video:
                             format_info = {
                                'format_id': fmt.get('format_id', ''),
                                'ext': fmt.get('ext', 'mp3'),
                                'quality': self._get_quality_display(fmt),
                                'filesize': self._format_filesize(fmt.get('filesize')),
                                'format_note': fmt.get('format_note', ''),
                                'vcodec': fmt.get('vcodec', 'none'),
                                'acodec': fmt.get('acodec', 'none'),
                                'width': fmt.get('width'),
                                'height': fmt.get('height'),
                                'fps': fmt.get('fps'),
                                'type': 'audio_only'
                            }
                             formats.append(format_info)
                        # ---
                
                # Organize formats
                video_data['formats'] = self._organize_formats(formats)
                
                # Add recommended formats (which will now use the new logic)
                video_data['recommended_formats'] = self._get_recommended_formats(info) # Pass info dictionary
                
                return video_data
                
        except Exception as e:
            logger.error(f"Info extraction failed: {e}")
            raise Exception(f"Could not fetch video info: {str(e)}")
    
    def download_video(self, url, format_id='best'):
        """Download video from any platform"""
        filepath = None
        temp_dir = tempfile.gettempdir()
        
        try:
            # Generate unique filename
            file_id = uuid.uuid4().hex
            filename_base = f"download_{file_id}"
            filepath_no_ext = os.path.join(temp_dir, filename_base)
            
            # Default options (will be overridden below)
            ydl_opts = {
                'outtmpl': filepath_no_ext + '.%(ext)s',
                'format': format_id, # Default if specific logic isn't matched
                'postprocessors': [],
            }
            
            # --- Updated Logic for Format Selection ---
            
            # 1. Audio-only download (MP3, good quality)
            if format_id == 'bestaudio_mp3':
                # Select best audio, convert to MP3
                ydl_opts.update({
                    'format': 'bestaudio', # Selects the best audio format
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192', # Good quality (192kbps)
                    }],
                    'postprocessor_args': [
                        '-movflags', 'faststart', # Good practice for web delivery
                    ],
                    'outtmpl': filepath_no_ext + '.mp3',
                })
            
            # 2. Video with Audio (MP4, specific quality)
            elif format_id.endswith('p_mp4'):
                # Extract resolution (e.g., '720' from '720p_mp4')
                resolution = format_id.split('p_mp4')[0]
                
                # Format string: best video at that height + best audio
                # Merging (webm/mp4 to mp4) and re-encoding is handled by yt-dlp/FFmpeg
                format_string = f"bestvideo[ext=mp4][height<={resolution}]+bestaudio[ext=m4a]/bestvideo[height<={resolution}]+bestaudio"
                
                ydl_opts.update({
                    'format': format_string,
                    'outtmpl': filepath_no_ext + '.mp4',
                    'postprocessors': [
                        {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'} # Ensure final output is MP4
                    ],
                    'postprocessor_args': [
                        '-movflags', 'faststart',
                    ],
                })
            
            # 3. Fallback/Other (like 'best')
            else:
                # Use a combined format string for 'best' to ensure video and audio are merged
                ydl_opts.update({
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
                    'outtmpl': filepath_no_ext + '.mp4',
                    'postprocessors': [
                        {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'} # Ensure final output is MP4
                    ],
                    'postprocessor_args': [
                        '-movflags', 'faststart',
                    ],
                })
                
            # --- End of Updated Logic ---

            logger.info(f"Starting download: {url} with format: {format_id}")
            
            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find downloaded file (need to check for .mp3 or .mp4)
            found_ext = 'mp4' if 'mp4' in ydl_opts['outtmpl'] else ('mp3' if 'mp3' in ydl_opts['outtmpl'] else '')
            
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base) and (found_ext == '' or f.endswith(f'.{found_ext}')):
                    filepath = os.path.join(temp_dir, f)
                    break
            
            if not filepath or not os.path.exists(filepath):
                raise Exception("Downloaded file not found")
            
            if os.path.getsize(filepath) == 0:
                raise Exception("Downloaded file is empty")
            
            logger.info(f"Download completed: {filepath}")
            return filepath
            
        except Exception as e:
            # Cleanup on error
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            raise Exception(f"Download failed: {str(e)}")
    
    # --- Helper Methods remain mostly the same, with one small change in _get_recommended_formats ---
    
    def _organize_formats(self, formats):
        """Organize formats by quality"""
        
        # Filter for the desired video qualities (144p, 240p, 360p, 480p, 720p, 1080p)
        filtered_video = [
            f for f in formats 
            if f.get('type') == 'video_with_audio' and f.get('height') in ALLOWED_VIDEO_QUALITIES
        ]
        
        # Pure audio formats
        audio_formats = [f for f in formats if f.get('type') == 'audio_only']

        # Sort video by resolution
        filtered_video.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
        # Sort audio by quality
        audio_formats.sort(key=lambda x: self._get_audio_quality(x), reverse=True)
        
        return filtered_video + audio_formats
    
    def _get_recommended_formats(self, info):
        """Get recommended formats based on required qualities and audio preference"""
        recommended = []
        
        # Available heights in the source video formats
        available_heights = set()
        if 'formats' in info:
            for fmt in info['formats']:
                if fmt.get('height') and fmt.get('vcodec') != 'none':
                    available_heights.add(fmt['height'])
        
        # 1. Video with Audio (MP4) - Specific Qualities
        for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
            if height in available_heights:
                 recommended.append({
                    'id': f'{height}p_mp4',
                    'name': f'Video + Audio ({height}p MP4)',
                    'format_id': f'{height}p_mp4', # Custom ID for download logic
                    'quality': f'{height}p MP4',
                    'size': 'Calculating...'
                })
        
        # 2. Best Audio (MP3) - One Good Quality
        # We don't need to check for a specific format ID, we'll use a fixed 'bestaudio_mp3' ID
        recommended.append({
            'id': 'bestaudio_mp3',
            'name': 'Audio Only (Good Quality MP3)',
            'format_id': 'bestaudio_mp3', # Custom ID for download logic
            'quality': 'MP3 (192kbps)',
            'size': 'Calculating...'
        })
        
        return recommended
    
    def _format_duration(self, seconds):
        if not seconds: return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def _format_filesize(self, bytes_size):
        if not bytes_size: return "Unknown"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
    
    def _get_quality_display(self, fmt):
        if fmt.get('height'):
            return f"{fmt['height']}p"
        elif fmt.get('acodec') != 'none':
            return 'Audio'
        return fmt.get('ext', 'unknown').upper()
    
    def _get_audio_quality(self, fmt):
        quality_map = {'best': 100, '320': 90, '256': 80, '192': 70, '128': 60}
        format_note = fmt.get('format_note', '').lower()
        for key, score in quality_map.items():
            if key in format_note:
                return score
        return 50

# Initialize downloader
downloader = UniversalVideoDownloader()

# Routes
@app.route('/')
def home():
    return jsonify({
        'message': 'Universal Video Downloader API',
        'status': 'running',
        'supported_sites': '1000+ sites via yt-dlp'
    })

@app.route('/api/info', methods=['POST', 'GET'])
def get_video_info_route(): # Renamed function to avoid conflict
    """Get video info from ANY supported platform"""
    try:
        # Get URL
        if request.method == 'GET':
            url = request.args.get('url', '').strip()
        else:
            data = request.get_json() or {}
            url = data.get('url', '').strip()
        
        logger.info(f"Processing URL: {url}")
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Validate URL using yt-dlp
        if not downloader.validate_url(url):
            return jsonify({
                'error': 'URL not supported',
                'message': 'This website is not supported by the downloader',
                'supported_sites': '1000+ sites including YouTube, Facebook, Instagram, Twitter, TikTok, etc.'
            }), 400
        
        # Get video info
        video_info = downloader.get_video_info(url)
        
        # Remove the internal 'type' key from formats before sending
        for fmt in video_info.get('formats', []):
            if 'type' in fmt:
                del fmt['type']
                
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video_route(): # Renamed function to avoid conflict
    """Download video from ANY platform"""
    filepath = None
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Download video
        filepath = downloader.download_video(url, format_id)
        
        # --- Updated Logic for Filename and MIME type ---
        filename = "download.file"
        mimetype = 'application/octet-stream'
        
        if format_id == 'bestaudio_mp3':
            filename = "download.mp3"
            mimetype = 'audio/mpeg'
        elif format_id.endswith('p_mp4') or format_id == 'best':
             filename = "download.mp4"
             mimetype = 'video/mp4'
        # ---
        
        response = send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
        # Cleanup after send
        @response.call_on_close
        def cleanup():
            try:
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
        
        return response
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/supported-sites')
def get_supported_sites_route(): # Renamed function to avoid conflict
    """Get list of all supported sites"""
    try:
        sites = downloader.get_supported_sites()
        return jsonify({
            'count': len(sites),
            'sites': sorted(list(sites))[:100]  # First 100 sites
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Universal Video Downloader'})

if __name__ == '__main__':
    logger.info("🚀 Universal Video Downloader Started")
    logger.info("📺 Supports 1000+ sites via yt-dlp")
    # Set `debug=False` for production environment
    app.run(host='0.0.0.0', port=5000, debug=True)
