from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import os
import tempfile
import uuid
import logging
import re
import shutil
import subprocess

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- AWS Elastic Beanstalk Configuration ---
# Beanstalk par, 'application' naam zaroori hai
application = Flask(__name__) 

# --- SECURITY CONFIGURATION: CORS & Rate Limiting ---
# Apne production domain se badal len
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com" 
CORS(application, origins=[ALLOWED_ORIGIN], supports_credentials=True)

# Rate Limiter: IP address ke mutabiq requests ko mehdood karna
limiter = Limiter(
    key_func=get_remote_address,
    app=application,
    default_limits=["60 per minute"], # Har IP se 60 requests per minute ki ijazat
    storage_uri="memory://" # Chote deployments ke liye memory store
)
# ---

# --- Quality Configuration ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]

class UniversalDownloader:
    def __init__(self):
        # YDL options. FFmpeg_location system wide use hoga.
        self.ydl_opts = {
            'quiet': True, # Production mein quiet mode behtar hai
            'no_warnings': True,
            'external_downloader_args': ['-movflags', 'faststart'],
            'postprocessors': [],
            # FFmpeg is expected to be installed system wide via .ebextensions
        }
    
    # --- Health Check for FFmpeg ---
    def check_ffmpeg(self):
        """Checks if ffmpeg is available in the system PATH"""
        try:
            subprocess.run(['ffmpeg', '-version'], 
                          capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def validate_url(self, url):
        """Validate if URL is supported by yt-dlp"""
        if not url or not isinstance(url, str):
            return False
        try:
            # Quick check only
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                ydl.extract_info(url, download=False, process=False)
                return True
        except:
            return False
    
    def search_videos(self, query):
        """Search videos on YouTube using yt-dlp's search functionality"""
        # (Search method remains the same as before)
        try:
            if not query: return []
            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'default_search': 'ytsearch10', 
                'extract_flat': 'in_playlist',
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

    def get_video_info(self, url):
        """Get video information and generate download links for all required qualities"""
        # (Info method remains the same, relying on FFmpeg for merge formats)
        try:
            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'extract_flat': False,
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # ... (rest of the logic to generate video_data and formats remains the same)
                video_data = {
                    'success': True,
                    'title': info.get('title', 'Unknown Title'),
                    'thumbnail': info.get('thumbnail', ''),
                    'extractor': info.get('extractor', 'Unknown Platform'),
                    'formats': [],
                }
                
                video_formats = []
                for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
                    # FFmpeg merge command
                    format_string = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/{height}p/best[height<={height}]"
                    custom_id = f'{height}p_mp4_merged'
                    video_formats.append({
                        'id': custom_id,
                        'name': f'Video + Audio ({height}p MP4)', 
                        'format_id': format_string, 
                        'quality': f'{height}p',
                        'ext': 'mp4',
                        'size': 'Estimating...',
                    })
                        
                audio_format = {
                    'id': 'bestaudio_mp3_converted',
                    'name': 'Audio Only (MP3 - High Quality)',
                    'format_id': 'bestaudio/best',
                    'quality': 'Audio',
                    'size': 'Estimating...',
                    'ext': 'mp3' 
                }

                video_data['formats'] = video_formats + [audio_format]
                return video_data

        except Exception as e:
            logger.error(f"Info extraction failed: {e}")
            raise Exception(f"Could not fetch video info: {str(e)}")

    def download_video(self, url, format_id):
        # (Download method is FIXED and uses PostProcessors relying on system FFmpeg)
        filepath = None
        temp_dir = tempfile.gettempdir()
        
        try:
            file_id = uuid.uuid4().hex
            filename_base = f"download_{file_id}"
            is_audio_conversion = (format_id == 'bestaudio/best')

            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'outtmpl': os.path.join(temp_dir, filename_base + '.%(ext)s'),
                'format': format_id,
                'postprocessors': [],
                'merge_output_format': 'mp4', 
            })
            
            if is_audio_conversion:
                ydl_opts.update({
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192', 
                    }],
                    'outtmpl': os.path.join(temp_dir, filename_base + '.mp3'),
                })
            
            else:
                ydl_opts['postprocessors'].append(
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                )
                ydl_opts['outtmpl'] = os.path.join(temp_dir, filename_base + '.mp4')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # --- Find the final file ---
            download_ext = 'mp3' if is_audio_conversion else 'mp4'
            downloaded_file = None
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base) and f.endswith(f'.{download_ext}'):
                    downloaded_file = os.path.join(temp_dir, f)
                    break
            
            if not downloaded_file or os.path.getsize(downloaded_file) == 0:
                raise Exception("Downloaded file not found or is empty. Check FFmpeg installation.")
            
            return downloaded_file
            
        except Exception as e:
            # Cleanup on failure
            if filepath and os.path.exists(filepath):
                try: os.remove(filepath)
                except: pass
            
            raise Exception(f"Download failed: {str(e)}")
            
    # --- Helper methods ---
    def _format_duration(self, seconds):
        if not seconds: return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"


# Initialize downloader
downloader = UniversalDownloader()

# --- ROUTES ---

@application.route('/health')
def health_check():
    """Route for AWS Beanstalk/Load Balancer to check system health and FFmpeg"""
    ffmpeg_ok = downloader.check_ffmpeg()
    
    if ffmpeg_ok:
         return jsonify({"status": "healthy", "ffmpeg_available": True}), 200
    else:
         # Beanstalk ko batana ki service theek nahi hai
         return jsonify({"status": "degraded", "error": "FFmpeg not found. Check .ebextensions."}), 503

@application.route('/')
def home():
    # ... (Home route remains the same)
    return jsonify({
        'message': 'Universal Downloader API (Production Stack)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'note': 'FFmpeg is installed via .ebextensions, high-res audio is supported.',
    })

@application.route('/api/info', methods=['POST'])
@limiter.limit("5 per minute") # Info request par sakht limit
@cross_origin(origins=[ALLOWED_ORIGIN])
def get_video_info_route():
    # ... (Info route remains the same)
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not downloader.validate_url(url):
            return jsonify({'error': 'URL not supported'}), 400
        
        video_info = downloader.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info error: {e}")
        return jsonify({'error': str(e)}), 500

@application.route('/api/download', methods=['POST'])
@limiter.limit("2 per minute") # Download request par sakht limit
@cross_origin(origins=[ALLOWED_ORIGIN])
def download_video_route():
    # ... (Download route remains the same with added file cleanup logic)
    filepath = None
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        
        if not url or not format_id:
            return jsonify({'error': 'URL and format_id are required'}), 400
        
        filepath = downloader.download_video(url, format_id)
        
        # Enhanced Filename and MIME type logic
        if 'audio' in format_id:
            filename = "download.mp3"
            mimetype = 'audio/mpeg'
        else:
             title = downloader.get_video_info(url).get('title', 'video')
             safe_title = re.sub(r'[^\w\-_\.]', '_', title)[:50]
             filename = f"{safe_title}.mp4"
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
        # Final safety cleanup (duplicated for robustness)
        if filepath and os.path.exists(filepath):
            try: os.remove(filepath)
            except: pass
        return jsonify({'error': str(e)}), 500

@application.route('/api/search', methods=['POST'])
@limiter.limit("10 per minute")
@cross_origin(origins=[ALLOWED_ORIGIN])
def search_videos_route():
    # ... (Search route remains the same)
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
    # Local Testing ke liye (AWS Beanstalk khud gunicorn ke zariye run karta hai)
    application.run(host='0.0.0.0', port=os.environ.get('PORT', 8080), debug=True)
