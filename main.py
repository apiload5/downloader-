# main.py - Video Downloader Backend API
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging
from urllib.parse import urlparse
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
CACHE_DURATION = 3600  # 1 hour
SUPPORTED_PLATFORMS = [
    'youtube', 'youtu.be', 'facebook', 'fb.watch', 
    'instagram', 'tiktok', 'dailymotion', 'twitter', 'x.com',
    'vimeo', 'twitch', 'bilibili', 'rutube', 'ok.ru',
    'likee', 'netflix', 'pinterest', 'reddit', 'snapchat'
]

# In-memory cache for video info
video_info_cache = {}
download_cache = {}

class VideoDownloaderAPI:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

    def validate_url(self, url):
        """Validate if URL is from supported platform"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            for platform in SUPPORTED_PLATFORMS:
                if platform in domain:
                    return True
            return False
        except Exception:
            return False

    def get_video_info(self, url):
        """Extract video information using yt-dlp"""
        cache_key = f"info_{url}"

        # Check cache first
        if cache_key in video_info_cache:
            cached_data = video_info_cache[cache_key]
            if datetime.now() < cached_data['expires']:
                logger.info(f"Returning cached info for {url}")
                return cached_data['data']

        try:
            logger.info(f"Fetching video info for: {url}")

            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Format response
                video_data = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'formats': []
                }

                # Extract available formats
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('filesize') and fmt['filesize'] > MAX_FILE_SIZE:
                            continue

                        format_info = {
                            'format_id': fmt.get('format_id', ''),
                            'ext': fmt.get('ext', ''),
                            'quality': self.get_quality_display(fmt),
                            'filesize': self.format_filesize(fmt.get('filesize')),
                            'format_note': fmt.get('format_note', ''),
                            'url': fmt.get('url', '')
                        }

                        # Only add video/audio formats
                        if fmt.get('vcodec') != 'none' or fmt.get('acodec') != 'none':
                            formats.append(format_info)

                # Sort formats by quality
                video_data['formats'] = sorted(formats, key=lambda x: self.get_quality_score(x['quality']), reverse=True)

                # Cache the result
                video_info_cache[cache_key] = {
                    'data': video_data,
                    'expires': datetime.now() + timedelta(seconds=CACHE_DURATION)
                }

                logger.info(f"Successfully fetched info for: {video_data['title']}")
                return video_data

        except Exception as e:
            logger.error(f"Error extracting video info: {str(e)}")
            raise Exception(f"Could not extract video information: {str(e)}")

    def download_video(self, url, format_id, quality):
        """Download video in specified format"""
        cache_key = f"download_{url}_{format_id}"

        # Check cache first
        if cache_key in download_cache:
            cached_file = download_cache[cache_key]
            if datetime.now() < cached_file['expires'] and os.path.exists(cached_file['path']):
                logger.info(f"Returning cached download for {url}")
                return cached_file['path']

        try:
            logger.info(f"Downloading video: {url} with format {format_id}")

            # Create temporary file
            temp_dir = tempfile.gettempdir()
            filename = f"video_{uuid.uuid4().hex}.mp4"
            filepath = os.path.join(temp_dir, filename)

            # Download options
            download_opts = {
                'outtmpl': filepath,
                'format': format_id or 'best',
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])

            # Verify file was created
            if not os.path.exists(filepath):
                raise Exception("Download failed - file not created")

            # Cache the file path
            download_cache[cache_key] = {
                'path': filepath,
                'expires': datetime.now() + timedelta(seconds=CACHE_DURATION)
            }

            logger.info(f"Successfully downloaded: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            raise Exception(f"Download failed: {str(e)}")

    def format_duration(self, seconds):
        """Format duration in seconds to HH:MM:SS"""
        if not seconds:
            return "Unknown"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    def format_filesize(self, bytes_size):
        """Format file size in human readable format"""
        if not bytes_size:
            return "Unknown"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"

    def get_quality_display(self, fmt):
        """Get quality display string"""
        if fmt.get('height'):
            return f"{fmt['height']}p"
        elif fmt.get('format_note'):
            return fmt['format_note']
        elif fmt.get('ext'):
            return fmt['ext'].upper()
        else:
            return "Unknown"

    def get_quality_score(self, quality):
        """Score quality for sorting"""
        if not quality:
            return 0

        # Extract numeric value
        import re
        match = re.search(r'(\d+)', quality)
        if match:
            return int(match.group(1))

        # Audio quality scores
        audio_scores = {
            'best': 1000,
            'worst': 0,
            'mp3': 500,
            'm4a': 500
        }

        return audio_scores.get(quality.lower(), 0)

# Initialize API
video_api = VideoDownloaderAPI()

# Routes
@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Get video information"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        if not video_api.validate_url(url):
            return jsonify({'error': 'Unsupported platform or invalid URL'}), 400

        video_info = video_api.get_video_info(url)
        return jsonify(video_info)

    except Exception as e:
        logger.error(f"Error in /api/info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video in specified format"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        quality = data.get('quality', '')

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        filepath = video_api.download_video(url, format_id, quality)
        filename = f"video_{uuid.uuid4().hex}.mp4"

        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4'
        )

    except Exception as e:
        logger.error(f"Error in /api/download: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'supported_platforms': SUPPORTED_PLATFORMS,
        'cache_size': {
            'video_info': len(video_info_cache),
            'downloads': len(download_cache)
        }
    })

@app.route('/api/platforms', methods=['GET'])
def get_supported_platforms():
    """Get list of supported platforms"""
    return jsonify({
        'platforms': SUPPORTED_PLATFORMS,
        'count': len(SUPPORTED_PLATFORMS),
        'message': f'Supports {len(SUPPORTED_PLATFORMS)}+ platforms'
    })

@app.route('/')
def home():
    """Home page with API documentation"""
    return jsonify({
        'message': 'Video Downloader API',
        'version': '1.0.0',
        'endpoints': {
            '/api/info': 'POST - Get video information',
            '/api/download': 'POST - Download video',
            '/api/health': 'GET - Health check',
            '/api/platforms': 'GET - Supported platforms'
        },
        'example_usage': {
            'get_info': {
                'method': 'POST',
                'url': '/api/info',
                'body': {'url': 'https://www.youtube.com/watch?v=...'}
            },
            'download': {
                'method': 'POST', 
                'url': '/api/download',
                'body': {
                    'url': 'https://www.youtube.com/watch?v=...',
                    'format_id': 'best',
                    'quality': '1080p'
                }
            }
        }
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'

    print(f"🚀 Video Downloader API Starting...")
    print(f"📍 Port: {port}")
    print(f"🔧 Debug: {debug}")
    print(f"📺 Supported Platforms: {len(SUPPORTED_PLATFORMS)}")
    print(f"🌐 API URL: http://localhost:{port}")
    print(f"✅ Health Check: http://localhost:{port}/api/health")

    app.run(host='0.0.0.0', port=port, debug=debug)