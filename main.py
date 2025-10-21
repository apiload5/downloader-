# main.py - FINAL PROFESSIONAL AND CLOUD-READY VERSION

# --- 1. Imports and Configuration ---
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging
import sys

# Configure a robust logging setup (Crucial for debugging in AWS CloudWatch)
# Set log level based on environment variable
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment Configuration
# Use environment variables for standard cloud hosting
PORT = int(os.environ.get('PORT', 5000))
DEBUG_MODE = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

# Supported Platforms (Remains the same, good practice)
SUPPORTED_PLATFORMS = [
    'youtube.com', 'youtu.be', 'facebook.com', 'fb.watch',
    'instagram.com', 'tiktok.com', 'twitter.com', 'x.com',
    'dailymotion.com'
]

# --- 2. Flask App Setup ---
app = Flask(__name__)
# Enable CORS for all origins, required for frontend
CORS(app) 
# Set max content length to prevent huge JSON/Form uploads (security)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB limit

# --- 3. Downloader Class (Advanced Logic) ---
class CloudVideoDownloader:
    def __init__(self):
        # Increased verbosity for better debug logs in the cloud environment
        self.ydl_opts = {
            'quiet': not DEBUG_MODE,
            'no_warnings': not DEBUG_MODE,
            'ignoreerrors': True,
            'logger': logger, # yt-dlp to use our configured logger
        }
    
    def validate_url(self, url):
        """URL validation"""
        # Improved error handling for URL validation
        return isinstance(url, str) and any(platform in url.lower() for platform in SUPPORTED_PLATFORMS)
    
    def get_video_info(self, url):
        """Get video information with all available formats and merged options"""
        try:
            logger.info(f"Fetching info for: {url}")
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("No video information found. Video may be private or restricted.")
                
                # Basic info extraction (Kept clean)
                thumbnail = info.get('thumbnail', '')
                video_data = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': thumbnail,
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'formats': []
                }
                
                # Process available formats
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('ext') in ('None', None) or not (fmt.get('vcodec') or fmt.get('acodec')):
                            continue
                        formats.append({
                            'format_id': fmt.get('format_id', ''),
                            'ext': fmt.get('ext', 'mp4'),
                            'quality': self.get_quality_display(fmt),
                            'filesize': self.format_filesize(fmt.get('filesize')),
                            'format_note': fmt.get('format_note', ''),
                            'vcodec': fmt.get('vcodec', 'none'),
                            'acodec': fmt.get('acodec', 'none')
                        })
                
                # Filter, sort, and add custom merged formats (Crucial for the service)
                video_data['formats'] = self.filter_and_sort_formats(formats)
                
                video_data['formats'].insert(0, {
                    'format_id': 'best_merged_mp4',
                    'ext': 'mp4',
                    'quality': 'Best Quality (MP4 - Merged)',
                    'filesize': 'Varies (Large)',
                    'format_note': 'Highest Video + Highest Audio (Requires FFmpeg)',
                    'vcodec': 'merged',
                    'acodec': 'merged'
                })
                
                video_data['formats'].append({
                    'format_id': 'bestaudio',
                    'ext': 'mp3',
                    'quality': 'Best Audio (MP3)',
                    'filesize': 'Varies',
                    'format_note': 'Audio Only Extraction (Requires FFmpeg)',
                    'vcodec': 'none',
                    'acodec': 'mp3'
                })
                
                return video_data
                
        except Exception as e:
            # More specific error for yt-dlp failures
            logger.error(f"Error in get_video_info for {url}: {e}", exc_info=True)
            raise Exception(f"Video information fetch failed. Possible region lock or unsupported format: {e}")
    
    def filter_and_sort_formats(self, formats):
        """Filter and sort formats properly: Prioritize combined streams, then resolution."""
        valid_formats = [f for f in formats if f['vcodec'] != 'none' or f['acodec'] != 'none']
        
        def get_sort_key(fmt):
            has_both = 1 if fmt['vcodec'] != 'none' and fmt['acodec'] != 'none' else 0
            height = 0
            try:
                # Extract resolution from quality string
                height = int(''.join(filter(str.isdigit, fmt['quality'])))
            except:
                pass
            
            # Sort order: 1. Combined stream, 2. Highest resolution
            return (-has_both, -height) 
        
        return sorted(valid_formats, key=get_sort_key)
    
    def download_video(self, url, format_id):
        """Download video using FFmpeg for high-quality merging and extraction."""
        final_filepath = None
        # Using a temporary directory is fine, but it needs strong cleanup.
        temp_dir = tempfile.gettempdir()
        download_opts = {}
        
        try:
            logger.info(f"Preparing download for: {url} with format {format_id}")
            
            # Use UUID to ensure a unique, traceable, and safe filename.
            filename_base = f"dl_{uuid.uuid4().hex}"
            filepath_no_ext = os.path.join(temp_dir, filename_base)
            
            if format_id == 'bestaudio':
                download_opts = {
                    'outtmpl': filepath_no_ext + '.%(ext)s', 
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192', 
                    }],
                }
                
            elif format_id == 'best_merged_mp4':
                # CRITICAL: Use `bestvideo+bestaudio/best` for best merging. 
                # This ensures the highest quality stream is selected and merged.
                download_opts = {
                    'outtmpl': filepath_no_ext + '.%(ext)s', 
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4'
                    }],
                }
                
            else:
                download_opts = {
                    'outtmpl': filepath_no_ext + '.%(ext)s',
                    'format': format_id or 'best[height<=720]',
                }

            download_opts.update({
                'quiet': not DEBUG_MODE, 
                'no_warnings': not DEBUG_MODE,
                'logger': logger,
                # Force re-download to prevent cache issues in concurrent requests
                'cachedir': False 
            })
            
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                # The crucial step that takes time
                ydl.download([url])
            
            # CRITICAL: Search for the final file by its unique prefix
            files = os.listdir(temp_dir)
            for f in files:
                if f.startswith(filename_base):
                    final_filepath = os.path.join(temp_dir, f)
                    break

            if not final_filepath or not os.path.exists(final_filepath) or os.path.getsize(final_filepath) == 0:
                raise Exception("Download failed - final file not found or is empty. Check FFmpeg installation and yt-dlp logs.")
            
            logger.info(f"Download successful: {final_filepath}")
            return final_filepath
            
        except Exception as e:
            logger.error(f"Download error: {e}", exc_info=True)
            # Ensure file cleanup on failure
            try:
                if final_filepath and os.path.exists(final_filepath):
                    os.remove(final_filepath)
                    logger.warning(f"Cleaned up partial file after failure: {final_filepath}")
            except Exception as clean_e:
                logger.error(f"Error during failed download cleanup: {clean_e}")
                
            raise Exception(f"Download processing failed: {e}")

    # Helper functions (Kept the same, they are good)
    def format_duration(self, seconds):
        if not seconds: return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def format_filesize(self, bytes_size):
        if not bytes_size: return "Unknown"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
    
    def get_quality_display(self, fmt):
        if fmt.get('height'):
            return f"{fmt['height']}p"
        elif fmt.get('format_note'):
            return fmt['format_note']
        elif fmt.get('ext') in ('m4a', 'webm') and fmt.get('acodec') != 'none':
            return 'Audio Only'
        return fmt.get('ext', 'unknown').upper()

# Initialize downloader object
downloader = CloudVideoDownloader()

# --- 4. Flask Routes (Cleanup Mechanism is Key) ---
@app.route('/api/info', methods=['POST'])
def get_video_info_route():
    # ... (Info route is now cleaner) ...
    try:
        data = request.get_json()
        url = data.get('url', '').strip() if data else None

        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not downloader.validate_url(url):
            return jsonify({'error': 'Unsupported platform or invalid URL format'}), 400
        
        video_info = downloader.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info request failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video_route():
    """Download video and clean up the file after sending."""
    filepath = None # Initialize outside try block for cleanup on failure
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best_merged_mp4') 
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # NOTE: This sync download will cause a timeout issue on AWS Load Balancer.
        # Professional solution requires a background task queue (Celery).
        filepath = downloader.download_video(url, format_id)
        
        # Determine proper filename and MIME type
        _, file_ext = os.path.splitext(filepath)
        final_file_ext = file_ext.lstrip('.')
        
        if format_id == 'bestaudio' or final_file_ext == 'mp3':
            # Use title in download name for better UX, but append UUID for uniqueness
            filename = f"audio_download_{uuid.uuid4().hex}.mp3"
            mimetype = 'audio/mpeg'
        else:
            filename = f"video_download_{uuid.uuid4().hex}.{final_file_ext}"
            mimetype = 'video/mp4' if final_file_ext == 'mp4' else 'application/octet-stream'


        # CRITICAL: Cleanup Hook for Professional Deployment
        # Ensures that the temporary file is deleted immediately after Flask sends it.
        @app.after_request
        def cleanup(response):
            # Capture the filepath in the closure for cleanup
            path_to_delete = filepath 
            try:
                if path_to_delete and os.path.exists(path_to_delete):
                    os.remove(path_to_delete)
                    logger.info(f"Cleaned up file: {path_to_delete}")
            except Exception as e:
                logger.error(f"Error cleaning up file {path_to_delete}: {e}")
            return response

        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
    except Exception as e:
        logger.error(f"Download API failed: {e}", exc_info=True)
        # Final safety cleanup on failure path (if filepath was set before failure)
        try:
            if filepath and os.path.exists(filepath):
                 os.remove(filepath)
        except:
             pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check for Load Balancers"""
    # Load balancers will hit this to check server status
    return jsonify({'status': 'healthy', 'service': 'Cloud Video Downloader'}), 200

@app.route('/')
def home():
    """Home page"""
    return jsonify({'message': 'Video Downloader API - Production Ready', 'status': 'Running'}), 200

# --- 5. WSGI Entry Point (Standard Cloud Deployment) ---
# Cloud platforms like Elastic Beanstalk and Docker look for 'application' variable by default.
# It is best practice to define the WSGI entry point this way.
application = app # Renaming 'app' to 'application' for standard WSGI compatibility

if __name__ == '__main__':
    print(f"🚀 Starting Cloud Video Downloader on port: {PORT}")
    application.run(host='0.0.0.0', port=PORT, debug=DEBUG_MODE)
