from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging
import sys

# Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 5000))
DEBUG_MODE = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

SUPPORTED_PLATFORMS = [
    'youtube.com', 'youtu.be', 'facebook.com', 'fb.watch',
    'instagram.com', 'tiktok.com', 'twitter.com', 'x.com',
    'dailymotion.com'
]

ALLOWED_ORIGINS = [
    "https://crispy0921.blogspot.com",
    "https://reqbin.com", 
    "http://localhost:3000",
    "http://127.0.0.1:5000"
]

app = Flask(__name__)
# Fixed CORS configuration
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

class CloudVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': not DEBUG_MODE,
            'no_warnings': not DEBUG_MODE,
            'ignoreerrors': True,
            'logger': logger,
            'socket_timeout': 30,
        }
    
    def validate_url(self, url):
        """Improved URL validation"""
        if not isinstance(url, str) or not url.strip():
            return False
        if not url.startswith(('http://', 'https://')):
            return False
        url_lower = url.lower()
        return any(platform in url_lower for platform in SUPPORTED_PLATFORMS)
    
    def get_video_info(self, url):
        # ... (your existing get_video_info method with the fixed sort key function)
        pass
    
    def download_video(self, url, format_id):
        # ... (your existing download_video method)
        pass
    
    # ... (your existing helper methods with fixed get_sort_key)

downloader = CloudVideoDownloader()

@app.route('/api/info', methods=['POST'])
def get_video_info_route():
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        url = data.get('url', '').strip()
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
    filepath = None
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best_merged_mp4') 
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        filepath = downloader.download_video(url, format_id)
        
        # Determine filename and MIME type
        _, file_ext = os.path.splitext(filepath)
        final_file_ext = file_ext.lstrip('.')
        
        if format_id == 'bestaudio' or final_file_ext == 'mp3':
            filename = f"audio_download.mp3"
            mimetype = 'audio/mpeg'
        else:
            filename = f"video_download.{final_file_ext}"
            mimetype = 'video/mp4' if final_file_ext == 'mp4' else 'application/octet-stream'

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
                    logger.info(f"Cleaned up file: {filepath}")
            except Exception as e:
                logger.error(f"Error cleaning up file {filepath}: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Download API failed: {e}", exc_info=True)
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as cleanup_error:
            logger.error(f"Cleanup error: {cleanup_error}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Cloud Video Downloader'}), 200

@app.route('/')
def home():
    return jsonify({'message': 'Video Downloader API - Production Ready', 'status': 'Running'}), 200

application = app

if __name__ == '__main__':
    print(f"🚀 Starting Cloud Video Downloader on port: {PORT}")
    application.run(host='0.0.0.0', port=PORT, debug=DEBUG_MODE)
