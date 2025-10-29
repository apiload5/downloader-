from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
import yt_dlp
import os
import tempfile
import uuid
import logging
import re
import math 
import shutil 

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- SECURITY CONFIGURATION: CORS ---
# sirf is domain ko ijazat hai
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com"
# CORS ko sirf ALLOWED_ORIGIN ke liye enable karein
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGIN}})
# ---

# --- Quality Configuration ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]

class UniversalDownloaderFixed:
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
            # Setting up a quick check with minimal processing
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'format': 'best',
                'skip_download': True,
                'nocheckcertificate': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=False, process=False)
                return True
        except Exception as e:
            logger.warning(f"URL validation failed for {url}: {e}")
            return False
    
    def get_video_info(self, url):
        """Get video information and generate download links for all required qualities"""
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
                
                # --- Format Generation Logic ---
                video_formats = []
                for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
                    # Simplified format string (Relies on FFmpeg Buildpack to merge streams if needed)
                    # We prioritize combined streams first, then separate video stream.
                    format_string = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
                    
                    # We use a custom format ID that includes the height for front-end clarity
                    custom_id = f'{height}p_mp4'
                    
                    video_formats.append({
                        'id': custom_id,
                        'name': f'Video + Audio (Max {height}p MP4)',
                        'format_id': format_string, 
                        'quality': f'{height}p',
                        'ext': 'mp4',
                        'size': 'Estimating...', 
                    })
                        
                # 2. Audio Only Format
                audio_format = {
                    'id': 'bestaudio_mp3',
                    'name': 'Audio Only (MP3 - Good Quality)',
                    'format_id': 'bestaudio/best', # Actual ytdlp audio format string
                    'quality': 'Audio',
                    'size': 'Estimating...',
                    'ext': 'mp3' 
                }

                # Prepare final lists
                video_data['formats'] = video_formats + [audio_format]
                
                return video_data
                
        except Exception as e:
            logger.error(f"Info extraction failed: {e}")
            raise Exception(f"Could not fetch video info: {str(e)}")

    def download_video(self, url, format_id):
        """Download video/audio using the simplified format string"""
        filepath = None
        # Use tempfile.gettempdir() for a safe, writable location on Heroku
        temp_dir = tempfile.gettempdir()
        
        try:
            file_id = uuid.uuid4().hex
            filename_base = f"download_{file_id}"
            
            is_audio_download = (format_id == 'bestaudio/best')

            ydl_opts = {
                # Output template: Use temp_dir and let yt-dlp determine the extension
                'outtmpl': os.path.join(temp_dir, filename_base + '.%(ext)s'),
                'format': format_id,
                'postprocessors': [],
                # Use mp4 merge format as we have installed FFmpeg buildpack
                'merge_output_format': 'mp4', 
            }
            
            # 1. Audio-only download: Add post-processor to convert to MP3 if needed
            if is_audio_download:
                ydl_opts['postprocessors'].append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                })
                # No need to set merge format as it's audio extraction
                del ydl_opts['merge_output_format']
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # --- Find and Rename Logic (Updated for stability) ---
            
            downloaded_file = None
            
            if is_audio_download:
                # Look for the mp3 file created by the post-processor
                downloaded_file = os.path.join(temp_dir, f"{filename_base}.mp3")
            else:
                # Look for the final merged mp4 file
                downloaded_file = os.path.join(temp_dir, f"{filename_base}.mp4")

            # Final check if file exists
            if not downloaded_file or not os.path.exists(downloaded_file):
                 # Fallback: check for any file starting with the base name
                for f in os.listdir(temp_dir):
                    if f.startswith(filename_base) and not f.endswith('.part'):
                        downloaded_file = os.path.join(temp_dir, f)
                        break
                
            if not downloaded_file or not os.path.exists(downloaded_file):
                 # This is the critical point of failure - try a lower quality next time.
                raise Exception("Downloaded file not found. Check logs for FFmpeg errors.")

            filepath = downloaded_file
            
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
            # Clearer message on failure
            raise Exception(f"Video Download failed: {str(e)}")
            
    # --- Search Functionality (Same as before) ---
    # (Rest of the search_videos and format functions are assumed to be here and unchanged)
    def search_videos(self, query):
        """Search videos on YouTube using yt-dlp's search functionality"""
        try:
            if not query:
                return []
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch10', 
                'extract_flat': 'in_playlist',
            }
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

    def _format_duration(self, seconds):
        if not seconds: return "Unknown"
        # ... (rest of function)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _format_filesize(self, bytes_size):
        if not bytes_size: return "Unknown"
        # ... (rest of function)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"


# Initialize downloader
downloader = UniversalDownloaderFixed()

# --- ROUTES ---

@app.route('/')
def home():
    return jsonify({
        'message': 'Universal Downloader API (SaveFrom/Y2Mate Style)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'supported_sites': '1000+ sites (via yt-dlp)',
        'note': 'FFmpeg Buildpack is required for high-quality downloads.',
        'available_endpoints': ['/api/info', '/api/download', '/api/search']
    })

@app.route('/api/info', methods=['POST'])
# cross_origin decorator ki yahan zaroorat nahi agar CORS(app, resources...) upar theek se set ho gaya hai
def get_video_info_route():
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
# cross_origin decorator ki yahan zaroorat nahi
def download_video_route():
    filepath = None
    try:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        
        if not url or not format_id:
            return jsonify({'error': 'URL and format_id are required'}), 400
        
        filepath = downloader.download_video(url, format_id)
        
        # Determine filename and MIME type
        if format_id == 'bestaudio/best':
            filename = "download.mp3"
            mimetype = 'audio/mpeg'
        else:
             filename = "download.mp4"
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
# cross_origin decorator ki yahan zaroorat nahi
def search_videos_route():
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

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Server is running'})

# Heroku gunicorn se run hota hai, isliye yeh block sirf local testing ke liye hai.
if __name__ == '__main__':
    # Flask ko sirf PORT environment variable use karne de
    app.run(debug=False)
