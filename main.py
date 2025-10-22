from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

class UniversalVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': False,
            'no_warnings': False,
        }
    
    def validate_url(self, url):
        """Validate if URL is supported by yt-dlp"""
        if not url or not isinstance(url, str):
            return False
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
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
                
                # Process available formats - ONLY STANDARD RESOLUTIONS
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        height = fmt.get('height', 0)
                        # Only include standard resolutions: 144p, 240p, 360p, 480p, 720p, 1080p
                        if height in [144, 240, 360, 480, 720, 1080]:
                            if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                                format_info = {
                                    'format_id': fmt.get('format_id', ''),
                                    'ext': fmt.get('ext', 'mp4'),
                                    'quality': f"{height}p",
                                    'filesize': self._format_filesize(fmt.get('filesize')),
                                    'format_note': fmt.get('format_note', ''),
                                    'vcodec': fmt.get('vcodec', 'none'),
                                    'acodec': fmt.get('acodec', 'none'),
                                    'width': fmt.get('width'),
                                    'height': height,
                                    'fps': fmt.get('fps'),
                                }
                                formats.append(format_info)
                
                # Sort formats by resolution
                video_data['formats'] = sorted(formats, key=lambda x: x['height'], reverse=True)
                
                # Add merged formats (video + audio combined)
                video_data['recommended_formats'] = self._get_recommended_formats(video_data['formats'])
                
                return video_data
                
        except Exception as e:
            logger.error(f"Info extraction failed: {e}")
            raise Exception(f"Could not fetch video info: {str(e)}")
    
    def download_video(self, url, format_id='best'):
        """Download video with proper audio merging"""
        filepath = None
        temp_dir = tempfile.gettempdir()
        
        try:
            # Generate unique filename
            file_id = uuid.uuid4().hex
            filename_base = f"download_{file_id}"
            filepath_no_ext = os.path.join(temp_dir, filename_base)
            
            # Download options based on format
            ydl_opts = {
                'outtmpl': filepath_no_ext + '.%(ext)s',
            }
            
            if format_id == 'bestaudio':
                # Audio only - MP3
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
            elif format_id.startswith('bestvideo+bestaudio'):
                # Merged video + audio (HIGH QUALITY)
                ydl_opts.update({
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4'
                    }],
                })
            elif format_id in ['144', '240', '360', '480', '720', '1080']:
                # Specific resolution with audio
                ydl_opts.update({
                    'format': f'bestvideo[height<={format_id}][ext=mp4]+bestaudio[ext=m4a]/best[height<={format_id}][ext=mp4]/best',
                    'merge_output_format': 'mp4',
                })
            else:
                # Default: best quality with audio
                ydl_opts.update({
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                })
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            logger.info(f"Download options: {ydl_opts}")
            
            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find downloaded file
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base):
                    filepath = os.path.join(temp_dir, f)
                    break
            
            if not filepath or not os.path.exists(filepath):
                raise Exception("Downloaded file not found")
            
            if os.path.getsize(filepath) == 0:
                raise Exception("Downloaded file is empty")
            
            logger.info(f"Download completed: {filepath} (Size: {os.path.getsize(filepath)} bytes)")
            return filepath
            
        except Exception as e:
            # Cleanup on error
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            raise Exception(f"Download failed: {str(e)}")
    
    def _get_recommended_formats(self, formats):
        """Get recommended formats with proper audio merging"""
        recommended = []
        
        # Standard resolutions with audio
        resolutions = [1080, 720, 480, 360, 240, 144]
        
        for res in resolutions:
            # Check if this resolution exists in available formats
            format_exists = any(f['height'] == res for f in formats)
            if format_exists:
                recommended.append({
                    'id': str(res),
                    'name': f'{res}p MP4 (Video+Audio)',
                    'format_id': str(res),
                    'quality': f'{res}p',
                    'type': 'video'
                })
        
        # Best quality merged video
        recommended.insert(0, {
            'id': 'bestvideo+bestaudio',
            'name': 'Best Quality MP4 (Video+Audio)',
            'format_id': 'bestvideo+bestaudio',
            'quality': 'Highest',
            'type': 'video'
        })
        
        # Audio only
        recommended.append({
            'id': 'bestaudio',
            'name': 'Best Audio MP3',
            'format_id': 'bestaudio',
            'quality': '192kbps',
            'type': 'audio'
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

# Initialize downloader
downloader = UniversalVideoDownloader()

# Routes
@app.route('/')
def home():
    return jsonify({
        'message': 'Universal Video Downloader API',
        'status': 'running',
        'supported_sites': '1000+ sites via yt-dlp',
        'features': 'Video+Audio merge, MP4/MP3 formats, Standard resolutions'
    })

@app.route('/api/info', methods=['POST', 'GET'])
def get_video_info():
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
                'message': 'This website is not supported by the downloader'
            }), 400
        
        # Get video info
        video_info = downloader.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video from ANY platform with audio"""
    filepath = None
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'bestvideo+bestaudio')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        logger.info(f"Download request - URL: {url}, Format: {format_id}")
        
        # Download video
        filepath = downloader.download_video(url, format_id)
        
        # Determine filename and MIME type
        if format_id == 'bestaudio':
            filename = "audio.mp3"
            mimetype = 'audio/mpeg'
        else:
            filename = "video.mp4"
            mimetype = 'video/mp4'
        
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
                    logger.info(f"Cleaned up: {filepath}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Video Downloader with Audio'})

if __name__ == '__main__':
    logger.info("🚀 Video Downloader Started - With Audio Support")
    logger.info("📺 Supports: 144p, 240p, 360p, 480p, 720p, 1080p with Audio")
    logger.info("🎵 Audio: MP3 192kbps")
    app.run(host='0.0.0.0', port=5000, debug=True)
