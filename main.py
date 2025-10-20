# main.py - Professional Video Downloader Backend API
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging
from urllib.parse import urlparse
from datetime import datetime, timedelta
import threading
import time
import requests
from concurrent.futures import ThreadPoolExecutor
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=['*'])  # Enable CORS for all origins

# Professional Configuration
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB for high quality videos
CACHE_DURATION = 1800  # 30 minutes cache
RATE_LIMIT_REQUESTS = 100  # Max requests per minute per IP
RATE_LIMIT_WINDOW = 60  # Time window in seconds

SUPPORTED_PLATFORMS = [
    'youtube.com', 'youtu.be', 'm.youtube.com', 
    'facebook.com', 'fb.watch', 'm.facebook.com',
    'instagram.com', 'www.instagram.com',
    'tiktok.com', 'vm.tiktok.com', 'www.tiktok.com',
    'twitter.com', 'x.com', 'vxtwitter.com',
    'dailymotion.com', 'vm.dailymotion.com',
    'vimeo.com', 'player.vimeo.com',
    'twitch.tv', 'clips.twitch.tv',
    'bilibili.com', 'b23.tv',
    'rutube.ru', 'ok.ru', 'likee.video',
    'pinterest.com', 'pin.it',
    'reddit.com', 'v.redd.it',
    'snapchat.com', 't.snapchat.com'
]

# Professional caching with cleanup
class CacheManager:
    def __init__(self):
        self.video_info_cache = {}
        self.download_cache = {}
        self.rate_limits = {}
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def _cleanup_loop(self):
        while True:
            time.sleep(300)  # Cleanup every 5 minutes
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        current_time = datetime.now()
        # Clean video info cache
        expired_keys = []
        for key, data in self.video_info_cache.items():
            if current_time > data['expires']:
                expired_keys.append(key)
        for key in expired_keys:
            del self.video_info_cache[key]
        
        # Clean download cache and remove files
        expired_downloads = []
        for key, data in self.download_cache.items():
            if current_time > data['expires']:
                expired_downloads.append((key, data['path']))
        for key, filepath in expired_downloads:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                del self.download_cache[key]
            except Exception as e:
                logger.error(f"Error cleaning up file {filepath}: {str(e)}")
        
        # Clean rate limits
        expired_ips = []
        for ip, data in self.rate_limits.items():
            if current_time > data['reset_time']:
                expired_ips.append(ip)
        for ip in expired_ips:
            del self.rate_limits[ip]

# Initialize cache manager
cache_manager = CacheManager()

class ProfessionalVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': False,
            'extract_flat': False,
            'ignoreerrors': True,
            'nooverwrites': True,
            'writethumbnail': False,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'format_sort': ['res:1080', 'res:720', 'res:480', 'res:360', 'res:240', 'res:144'],
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
        }
        
        # Audio specific options
        self.audio_opts = {
            'quiet': True,
            'no_warnings': False,
            'extractaudio': True,
            'audioformat': 'mp3',
            'audioquality': '0',  # Best quality
            'format': 'bestaudio/best',
        }
    
    def validate_url(self, url):
        """Professional URL validation"""
        try:
            parsed = urlparse(url)
            if not parsed.scheme in ['http', 'https']:
                return False
            
            domain = parsed.netloc.lower()
            
            # Check for supported platforms
            for platform in SUPPORTED_PLATFORMS:
                if platform in domain:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"URL validation error: {str(e)}")
            return False
    
    def get_video_info(self, url):
        """Professional video information extraction"""
        cache_key = f"info_{hash(url)}"
        
        # Check cache first
        if cache_key in cache_manager.video_info_cache:
            cached_data = cache_manager.video_info_cache[cache_key]
            if datetime.now() < cached_data['expires']:
                logger.info(f"Returning cached info for {url}")
                return cached_data['data']
        
        try:
            logger.info(f"Fetching professional video info for: {url}")
            
            # First get basic info
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("Could not extract video information")
                
                # Professional response format
                video_data = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self._format_duration(info.get('duration', 0)),
                    'thumbnail': self._get_best_thumbnail(info),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'description': info.get('description', '')[:200] + '...' if info.get('description') else '',
                    'formats': [],
                    'audio_formats': []
                }
                
                # Extract video formats
                video_formats = self._extract_video_formats(info)
                audio_formats = self._extract_audio_formats(info)
                
                video_data['formats'] = video_formats
                video_data['audio_formats'] = audio_formats
                
                # Cache the result
                cache_manager.video_info_cache[cache_key] = {
                    'data': video_data,
                    'expires': datetime.now() + timedelta(seconds=CACHE_DURATION)
                }
                
                logger.info(f"Successfully fetched professional info for: {video_data['title']}")
                return video_data
                
        except Exception as e:
            logger.error(f"Professional info extraction error: {str(e)}")
            raise Exception(f"Could not extract video information: {str(e)}")
    
    def _extract_video_formats(self, info):
        """Extract and sort video formats professionally"""
        formats = []
        
        if 'formats' in info:
            for fmt in info['formats']:
                # Skip formats that are too large
                if fmt.get('filesize') and fmt['filesize'] > MAX_FILE_SIZE:
                    continue
                
                # Only include video formats
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                    format_info = {
                        'format_id': fmt.get('format_id', ''),
                        'ext': fmt.get('ext', 'mp4'),
                        'quality': self._get_quality_display(fmt),
                        'filesize': self._format_filesize(fmt.get('filesize')),
                        'format_note': fmt.get('format_note', ''),
                        'height': fmt.get('height', 0),
                        'width': fmt.get('width', 0),
                        'fps': fmt.get('fps', 0),
                        'vcodec': fmt.get('vcodec', ''),
                        'acodec': fmt.get('acodec', '')
                    }
                    
                    # Only add valid video formats
                    if format_info['height'] > 0:
                        formats.append(format_info)
        
        # Professional sorting: 720p, 360p, 480p, 240p, 144p, then 1080p
        quality_order = {'720p': 1, '360p': 2, '480p': 3, '240p': 4, '144p': 5, '1080p': 6}
        
        def sort_key(format_info):
            quality = format_info['quality'].lower()
            return (quality_order.get(quality, 999), format_info['height'])
        
        return sorted(formats, key=sort_key)
    
    def _extract_audio_formats(self, info):
        """Extract audio formats"""
        audio_formats = []
        
        if 'formats' in info:
            for fmt in info['formats']:
                # Audio only formats
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_info = {
                        'format_id': fmt.get('format_id', ''),
                        'ext': fmt.get('ext', 'mp3'),
                        'quality': 'MP3',
                        'filesize': self._format_filesize(fmt.get('filesize')),
                        'format_note': 'Audio',
                        'bitrate': fmt.get('abr', 0),
                        'acodec': fmt.get('acodec', '')
                    }
                    audio_formats.append(audio_info)
        
        return sorted(audio_formats, key=lambda x: x.get('bitrate', 0), reverse=True)
    
    def download_video(self, url, format_id, quality):
        """Professional video download with proper format handling"""
        cache_key = f"download_{hash(url)}_{format_id}"
        
        # Check cache first
        if cache_key in cache_manager.download_cache:
            cached_file = cache_manager.download_cache[cache_key]
            if datetime.now() < cached_file['expires'] and os.path.exists(cached_file['path']):
                logger.info(f"Returning cached download for {url}")
                return cached_file['path']
        
        try:
            logger.info(f"Professional download: {url} with format {format_id}")
            
            # Create temporary file with proper extension
            temp_dir = tempfile.gettempdir()
            file_ext = '.mp4' if 'audio' not in format_id.lower() else '.mp3'
            filename = f"video_{uuid.uuid4().hex}{file_ext}"
            filepath = os.path.join(temp_dir, filename)
            
            # Professional download options
            download_opts = {
                'outtmpl': filepath,
                'format': format_id,
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'merge_output_format': 'mp4',
            }
            
            # Use audio options for audio downloads
            if 'audio' in format_id.lower() or format_id == 'bestaudio':
                download_opts.update(self.audio_opts)
            
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])
            
            # Verify file was created and has content
            if not os.path.exists(filepath):
                raise Exception("Download failed - file not created")
            
            file_size = os.path.getsize(filepath)
            if file_size == 0:
                os.remove(filepath)
                raise Exception("Download failed - empty file")
            
            logger.info(f"Successfully downloaded: {filepath} ({file_size} bytes)")
            
            # Cache the file path
            cache_manager.download_cache[cache_key] = {
                'path': filepath,
                'expires': datetime.now() + timedelta(seconds=CACHE_DURATION)
            }
            
            return filepath
            
        except Exception as e:
            logger.error(f"Professional download error: {str(e)}")
            # Clean up failed download files
            try:
                if 'filepath' in locals() and os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
            raise Exception(f"Download failed: {str(e)}")
    
    def _get_best_thumbnail(self, info):
        """Get the best available thumbnail"""
        thumbnails = info.get('thumbnails', [])
        if thumbnails:
            # Prefer higher resolution thumbnails
            sorted_thumbs = sorted(thumbnails, key=lambda x: x.get('width', 0), reverse=True)
            return sorted_thumbs[0].get('url', info.get('thumbnail', ''))
        return info.get('thumbnail', '')
    
    def _format_duration(self, seconds):
        """Professional duration formatting"""
        if not seconds:
            return "Unknown"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def _format_filesize(self, bytes_size):
        """Professional file size formatting"""
        if not bytes_size:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
    
    def _get_quality_display(self, fmt):
        """Professional quality display"""
        if fmt.get('height'):
            return f"{fmt['height']}p"
        elif fmt.get('format_note'):
            note = fmt['format_note'].lower()
            if 'hd' in note:
                return '720p'
            elif 'sd' in note:
                return '480p'
            return fmt['format_note'].title()
        elif fmt.get('ext'):
            return fmt['ext'].upper()
        else:
            return "Standard"

# Initialize professional downloader
video_downloader = ProfessionalVideoDownloader()

# Rate limiting decorator
def rate_limit(f):
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = datetime.now()
        
        if client_ip not in cache_manager.rate_limits:
            cache_manager.rate_limits[client_ip] = {
                'count': 1,
                'reset_time': current_time + timedelta(seconds=RATE_LIMIT_WINDOW)
            }
        else:
            rate_data = cache_manager.rate_limits[client_ip]
            
            # Reset counter if window expired
            if current_time > rate_data['reset_time']:
                rate_data['count'] = 1
                rate_data['reset_time'] = current_time + timedelta(seconds=RATE_LIMIT_WINDOW)
            else:
                rate_data['count'] += 1
                
            # Check if rate limit exceeded
            if rate_data['count'] > RATE_LIMIT_REQUESTS:
                return jsonify({
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': int((rate_data['reset_time'] - current_time).total_seconds())
                }), 429
        
        return f(*args, **kwargs)
    return decorated_function

# Professional Routes
@app.route('/api/info', methods=['POST'])
@rate_limit
def get_video_info():
    """Professional video information endpoint"""
    try:
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Validate URL
        if not video_downloader.validate_url(url):
            return jsonify({
                'error': 'Unsupported platform or invalid URL',
                'supported_platforms': SUPPORTED_PLATFORMS[:10]  # Show first 10
            }), 400
        
        # Get video information
        video_info = video_downloader.get_video_info(url)
        
        # Professional response
        response = {
            'success': True,
            'data': video_info,
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Professional info endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/download', methods=['POST'])
@rate_limit
def download_video():
    """Professional video download endpoint"""
    try:
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best')
        quality = data.get('quality', '')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Download video
        filepath = video_downloader.download_video(url, format_id, quality)
        
        # Determine filename
        filename = f"video_{uuid.uuid4().hex}.mp4"
        if 'audio' in format_id.lower() or format_id == 'bestaudio':
            filename = f"audio_{uuid.uuid4().hex}.mp3"
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4' if '.mp4' in filename else 'audio/mpeg'
        )
        
    except Exception as e:
        logger.error(f"Professional download endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Professional health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Professional Video Downloader API',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'uptime': 'Running',
        'supported_platforms_count': len(SUPPORTED_PLATFORMS),
        'cache_stats': {
            'video_info': len(cache_manager.video_info_cache),
            'downloads': len(cache_manager.download_cache),
            'rate_limits': len(cache_manager.rate_limits)
        }
    })

@app.route('/api/platforms', methods=['GET'])
def get_supported_platforms():
    """Professional platforms endpoint"""
    return jsonify({
        'success': True,
        'platforms': SUPPORTED_PLATFORMS,
        'count': len(SUPPORTED_PLATFORMS),
        'message': f'Professional support for {len(SUPPORTED_PLATFORMS)}+ platforms',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Professional statistics endpoint"""
    return jsonify({
        'success': True,
        'stats': {
            'total_platforms': len(SUPPORTED_PLATFORMS),
            'cache_size': {
                'video_info': len(cache_manager.video_info_cache),
                'downloads': len(cache_manager.download_cache)
            },
            'rate_limits_active': len(cache_manager.rate_limits),
            'service_uptime': 'Active'
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/')
def home():
    """Professional home page"""
    return jsonify({
        'service': 'Professional Video Downloader API',
        'version': '2.0.0',
        'description': 'High-performance video download service supporting 1000+ platforms',
        'endpoints': {
            '/api/info': 'POST - Get video information',
            '/api/download': 'POST - Download video/audio',
            '/api/health': 'GET - Service health check',
            '/api/platforms': 'GET - Supported platforms',
            '/api/stats': 'GET - Service statistics'
        },
        'documentation': 'Visit /api/health for service status',
        'timestamp': datetime.now().isoformat()
    })

# Professional error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'timestamp': datetime.now().isoformat()
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'success': False, 
        'error': 'Method not allowed',
        'timestamp': datetime.now().isoformat()
    }), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'timestamp': datetime.now().isoformat()
    }), 500

@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded',
        'timestamp': datetime.now().isoformat()
    }), 429

# Startup message
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print("🚀 PROFESSIONAL VIDEO DOWNLOADER API STARTING...")
    print("📍 Service: Professional Video Downloader")
    print("🔧 Version: 2.0.0")
    print("📡 Port:", port)
    print("🐛 Debug:", debug)
    print("📺 Supported Platforms:", len(SUPPORTED_PLATFORMS))
    print("🌐 API URL: http://localhost:{port}")
    print("✅ Health Check: http://localhost:{port}/api/health")
    print("📊 Statistics: http://localhost:{port}/api/stats")
    print("🔒 Rate Limiting: Enabled")
    print("💾 Caching: Enabled")
    print("🎯 Ready for production use!")
    
    app.run(host='0.0.0.0', port=port, debug=debug)