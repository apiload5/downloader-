from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
import yt_dlp
import os
import tempfile
import uuid
import logging
import re # For search functionality

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- SECURITY CONFIGURATION: CORS ---
# Only allow requests from your specific frontend domain.
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com"
CORS(app, origins=[ALLOWED_ORIGIN])
# ---

# --- Quality Configuration ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]

class UniversalDownloaderNoFFmpeg:
    def __init__(self):
        # yt-dlp options configured to AVOID forcing FFmpeg merging
        self.ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            # 'external_downloader': 'aria2c', # Optional for faster download, but not needed for Replit
        }
    
    def validate_url(self, url):
        """Validate if URL is supported by yt-dlp"""
        if not url or not isinstance(url, str):
            return False
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # Use extract_info to validate without downloading
                ydl.extract_info(url, download=False, process=False)
                return True
        except:
            return False
    
    def get_video_info(self, url):
        """Get video information and filter formats (No FFmpeg logic)"""
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
                
                video_data = {
                    'success': True,
                    'title': info.get('title', 'Unknown Title'),
                    'thumbnail': info.get('thumbnail', ''),
                    'extractor': info.get('extractor', 'Unknown Platform'),
                    'formats': [],
                }
                
                # --- Format Filtering Logic (No FFmpeg) ---
                available_formats = {}
                
                if 'formats' in info:
                    for fmt in info['formats']:
                        res = fmt.get('height')
                        # 1. Filter: Only formats with both video and audio (MP4 preferred)
                        if (fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none' and 
                            fmt.get('ext') in ['mp4', 'webm']) and res in ALLOWED_VIDEO_QUALITIES:
                            
                            # Keep the highest quality stream found for this resolution
                            if res not in available_formats or fmt.get('filesize') > available_formats[res].get('filesize', 0):
                                format_id = fmt.get('format_id')
                                available_formats[res] = {
                                    'id': format_id,
                                    'name': f'Video + Audio ({res}p {fmt.get("ext").upper()})',
                                    'format_id': format_id,
                                    'quality': f'{res}p',
                                    'ext': fmt.get('ext'),
                                    'size': self._format_filesize(fmt.get('filesize')),
                                }

                # 2. Audio Only Format
                # Use a placeholder ID that triggers the audio download logic later
                audio_format = {
                    'id': 'bestaudio_no_mp3_conversion',
                    'name': 'Audio Only (Best Quality - MP3 Placeholder)',
                    'format_id': 'bestaudio_no_mp3_conversion',
                    'quality': 'Audio',
                    'size': 'Estimating...',
                    'ext': 'mp3'
                }

                # Prepare final lists
                video_formats_list = list(available_formats.values())
                video_formats_list.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
                
                video_data['formats'] = video_formats_list + [audio_format]
                
                return video_data
                
        except Exception as e:
            logger.error(f"Info extraction failed: {e}")
            raise Exception(f"Could not fetch video info: {str(e)}")

    def download_video(self, url, format_id):
        """Download video/audio without FFmpeg dependency"""
        filepath = None
        temp_dir = tempfile.gettempdir()
        
        try:
            file_id = uuid.uuid4().hex
            filename_base = f"download_{file_id}"
            
            # Default options (for direct download)
            ydl_opts = {
                'outtmpl': os.path.join(temp_dir, filename_base + '.%(ext)s'),
                'postprocessors': [],
            }
            
            download_ext = 'mp4' 

            # 1. Audio-only download (No MP3 conversion)
            if format_id == 'bestaudio_no_mp3_conversion':
                # Select best audio, but do NOT add FFmpeg postprocessor
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    # We will get M4A/Opus, and simply rename the extension to MP3
                    'outtmpl': os.path.join(temp_dir, filename_base + '.mp3'),
                })
                download_ext = 'mp3'
                
            # 2. Video with Audio (Direct download using selected format ID)
            else:
                ydl_opts.update({
                    'format': format_id,
                })
                download_ext = 'mp4' # Or webm, based on the selected format
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find downloaded file
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base):
                    # Check for the expected extension or if it's the merged file
                    if f.endswith(f'.{download_ext}') or (format_id != 'bestaudio_no_mp3_conversion' and f.endswith('.mp4')):
                        filepath = os.path.join(temp_dir, f)
                        break
            
            if not filepath or not os.path.exists(filepath):
                raise Exception("Downloaded file not found. Try a lower quality.")
            
            if os.path.getsize(filepath) == 0:
                raise Exception("Downloaded file is empty")
            
            logger.info(f"Download completed: {filepath}")
            return filepath
            
        except Exception as e:
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            raise Exception(f"Download failed: {str(e)}")
            
    # --- Search Functionality ---
    def search_videos(self, query):
        """Search videos on YouTube using yt-dlp's search functionality"""
        try:
            if not query:
                return []
                
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch10',  # Search first 10 results on YouTube
                'extract_flat': 'in_playlist',  # Get basic info without full extraction
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # ytsearch: is the standard prefix for search queries
                info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                
                results = []
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            results.append({
                                'title': entry.get('title', 'Unknown Title'),
                                'url': entry.get('url', entry.get('webpage_url')),
                                'duration': self._format_duration(entry.get('duration')),
                                'thumbnail': entry.get('thumbnail'),
                                'uploader': entry.get('uploader'),
                                'id': entry.get('id')
                            })
                return results
                
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


    # --- Helper methods ---
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
downloader = UniversalDownloaderNoFFmpeg()

# --- ROUTES ---

@app.route('/')
def home():
    return jsonify({
        'message': 'Universal Downloader API (Replit Compatible)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'supported_sites': '1000+ sites (via yt-dlp)',
        'note': 'FFmpeg dependency removed by prioritizing combined video/audio formats.',
        'available_endpoints': ['/api/info', '/api/download', '/api/search']
    })

@app.route('/api/info', methods=['POST'])
@cross_origin(origins=[ALLOWED_ORIGIN])
def get_video_info_route():
    """Get video info from ANY supported platform"""
    # The CORS decorator handles the security check (if request origin is not ALLOWED_ORIGIN, it fails)
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not downloader.validate_url(url):
            return jsonify({
                'error': 'URL not supported',
                'message': 'This website is not supported by the downloader',
            }), 400
        
        video_info = downloader.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
@cross_origin(origins=[ALLOWED_ORIGIN])
def download_video_route():
    """Download video from ANY platform"""
    filepath = None
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        
        if not url or not format_id:
            return jsonify({'error': 'URL and format_id are required'}), 400
        
        filepath = downloader.download_video(url, format_id)
        
        # Determine filename and MIME type
        if format_id == 'bestaudio_no_mp3_conversion':
            filename = "download.mp3"
            mimetype = 'audio/mpeg'
        else:
             filename = "download.mp4" # Or webm
             mimetype = 'video/mp4'
        
        response = send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
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

@app.route('/api/search', methods=['POST'])
@cross_origin(origins=[ALLOWED_ORIGIN])
def search_videos_route():
    """Search videos on YouTube"""
    try:
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'error': 'Search query is required'}), 400
            
        results = downloader.search_videos(query)
        
        return jsonify({'results': results})
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 Universal Downloader Started (Replit/AWS-Lite Mode)")
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)
