from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import os
import tempfile
import uuid
import logging
import threading
import time
import re
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor
import json

# ==================== CONFIGURATION ====================
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 5000))
DEBUG_MODE = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

# ==================== SECURITY CONFIG ====================
ALLOWED_ORIGINS = [
    "https://crispy0921.blogspot.com",
    "http://localhost:3000",
    "http://127.0.0.1:5000",
    "*"  # Production mein specific domains daalo
]

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
MAX_DOWNLOAD_TIME = 300  # 5 minutes

# ==================== FLASK APP ====================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# ==================== SUPPORTED PLATFORMS ====================
SUPPORTED_PLATFORMS = {
    'youtube': [
        'youtube.com', 'youtu.be', 'm.youtube.com', 'www.youtube.com',
        'youtube-nocookie.com'
    ],
    'facebook': [
        'facebook.com', 'fb.com', 'fb.watch', 'www.facebook.com'
    ],
    'instagram': [
        'instagram.com', 'www.instagram.com', 'instagr.am'
    ],
    'tiktok': [
        'tiktok.com', 'www.tiktok.com', 'vm.tiktok.com'
    ],
    'twitter': [
        'twitter.com', 'x.com', 'www.twitter.com'
    ],
    'dailymotion': [
        'dailymotion.com', 'www.dailymotion.com'
    ],
    'vimeo': [
        'vimeo.com', 'www.vimeo.com'
    ],
    'likee': [
        'likee.video', 'likee.com'
    ]
}

# ==================== DOWNLOAD MANAGER ====================
class VideoDownloadManager:
    def __init__(self):
        self.downloads = {}
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self.cleanup_thread.start()
    
    def _cleanup_worker(self):
        """Cleanup expired downloads every minute"""
        while True:
            try:
                current_time = time.time()
                expired = []
                for download_id, data in self.downloads.items():
                    if current_time - data['timestamp'] > 3600:  # 1 hour
                        expired.append(download_id)
                        # Cleanup file
                        if 'filepath' in data and os.path.exists(data['filepath']):
                            try:
                                os.remove(data['filepath'])
                            except:
                                pass
                
                for download_id in expired:
                    del self.downloads[download_id]
                    
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                time.sleep(60)
    
    def add_download(self, download_id, data):
        self.downloads[download_id] = {
            **data,
            'timestamp': time.time()
        }
    
    def get_download(self, download_id):
        return self.downloads.get(download_id)
    
    def remove_download(self, download_id):
        if download_id in self.downloads:
            del self.downloads[download_id]

download_manager = VideoDownloadManager()

# ==================== VIDEO DOWNLOADER ====================
class ProfessionalVideoDownloader:
    def __init__(self):
        self.ydl_opts_base = {
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': False,
            'extract_flat': False,
            'socket_timeout': 30,
            'extractaudio': False,
            'noplaylist': True,
        }
    
    def validate_url(self, url):
        """Advanced URL validation"""
        if not url or not isinstance(url, str):
            return False
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme in ('http', 'https'):
                return False
            
            domain = parsed.netloc.lower()
            
            # Check all supported platforms
            for platform, domains in SUPPORTED_PATFORMS.items():
                for supported_domain in domains:
                    if supported_domain in domain:
                        return True
            
            return False
            
        except Exception:
            return False
    
    def extract_domain(self, url):
        """Extract domain from URL"""
        try:
            domain = urlparse(url).netloc.lower()
            for platform, domains in SUPPORTED_PLATFORMS.items():
                for supported_domain in domains:
                    if supported_domain in domain:
                        return platform
            return 'unknown'
        except:
            return 'unknown'
    
    def get_video_info(self, url):
        """Get comprehensive video information"""
        try:
            logger.info(f"Fetching info for: {url}")
            
            ydl_opts = {
                **self.ydl_opts_base,
                'extract_flat': False,
                'listformats': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("Video not found or inaccessible")
                
                # Basic info
                video_data = {
                    'id': info.get('id', ''),
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self._format_duration(info.get('duration')),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'description': info.get('description', '')[:200] + '...' if info.get('description') else '',
                    'platform': self.extract_domain(url),
                    'formats': []
                }
                
                # Process formats
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('vcodec') != 'none' or fmt.get('acodec') != 'none':
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
                                'url': fmt.get('url', '')
                            }
                            formats.append(format_info)
                
                # Sort and filter formats
                video_data['formats'] = self._organize_formats(formats)
                
                # Add recommended formats
                video_data['recommended_formats'] = self._get_recommended_formats(video_data['formats'])
                
                return video_data
                
        except Exception as e:
            logger.error(f"Info extraction failed: {e}", exc_info=True)
            raise Exception(f"Could not fetch video info: {str(e)}")
    
    def _organize_formats(self, formats):
        """Organize formats by quality and type"""
        video_formats = []
        audio_formats = []
        
        for fmt in formats:
            if fmt['vcodec'] != 'none' and fmt['acodec'] != 'none':
                # Combined video+audio
                video_formats.append(fmt)
            elif fmt['vcodec'] != 'none':
                # Video only
                video_formats.append(fmt)
            elif fmt['acodec'] != 'none':
                # Audio only
                audio_formats.append(fmt)
        
        # Sort video formats by resolution
        video_formats.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
        
        # Sort audio formats by quality
        audio_formats.sort(key=lambda x: self._get_audio_quality(x), reverse=True)
        
        return video_formats + audio_formats
    
    def _get_recommended_formats(self, formats):
        """Get recommended formats for quick download"""
        recommended = []
        
        # Best quality MP4
        best_mp4 = next((f for f in formats if f['ext'] == 'mp4' and f['vcodec'] != 'none'), None)
        if best_mp4:
            recommended.append({
                'id': 'best_mp4',
                'name': 'Best Quality MP4',
                'format_id': best_mp4['format_id'],
                'quality': best_mp4['quality'],
                'size': best_mp4['filesize']
            })
        
        # 720p MP4
        hd_mp4 = next((f for f in formats if f.get('height') == 720 and f['ext'] == 'mp4'), None)
        if hd_mp4:
            recommended.append({
                'id': '720p_mp4',
                'name': 'HD 720p MP4',
                'format_id': hd_mp4['format_id'],
                'quality': '720p',
                'size': hd_mp4['filesize']
            })
        
        # 480p MP4
        sd_mp4 = next((f for f in formats if f.get('height') == 480 and f['ext'] == 'mp4'), None)
        if sd_mp4:
            recommended.append({
                'id': '480p_mp4',
                'name': 'SD 480p MP4',
                'format_id': sd_mp4['format_id'],
                'quality': '480p',
                'size': sd_mp4['filesize']
            })
        
        # Best Audio
        best_audio = next((f for f in formats if f['acodec'] != 'none' and f['vcodec'] == 'none'), None)
        if best_audio:
            recommended.append({
                'id': 'best_audio',
                'name': 'Best Audio MP3',
                'format_id': best_audio['format_id'],
                'quality': 'Audio',
                'size': best_audio['filesize']
            })
        
        return recommended
    
    def download_video(self, url, format_id, download_id):
        """Download video with progress tracking"""
        filepath = None
        temp_dir = tempfile.gettempdir()
        
        try:
            # Generate unique filename
            filename = f"download_{download_id}.mp4"
            filepath = os.path.join(temp_dir, filename)
            
            # Download options
            ydl_opts = {
                **self.ydl_opts_base,
                'outtmpl': filepath,
                'format': format_id,
                'progress_hooks': [self._progress_hook],
            }
            
            # Add postprocessor for audio
            if format_id == 'bestaudio' or 'audio' in format_id.lower():
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
                filepath = filepath.replace('.mp4', '.mp3')
            
            # Update download status
            download_manager.add_download(download_id, {
                'status': 'downloading',
                'progress': 0,
                'filepath': filepath,
                'filename': os.path.basename(filepath)
            })
            
            # Start download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Verify download
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                raise Exception("Download failed - empty file")
            
            # Update status
            download_manager.add_download(download_id, {
                'status': 'completed',
                'progress': 100,
                'filepath': filepath,
                'filename': os.path.basename(filepath),
                'filesize': os.path.getsize(filepath)
            })
            
            return filepath
            
        except Exception as e:
            logger.error(f"Download failed: {e}", exc_info=True)
            # Cleanup failed download
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            
            download_manager.add_download(download_id, {
                'status': 'error',
                'error': str(e)
            })
            raise
    
    def _progress_hook(self, d):
        """Progress hook for yt-dlp"""
        if d['status'] == 'downloading':
            download_id = None
            # Extract download ID from filename
            filename = d.get('filename', '')
            if 'download_' in filename:
                try:
                    download_id = filename.split('download_')[1].split('.')[0]
                except:
                    pass
            
            if download_id and download_manager.get_download(download_id):
                percent = 0
                if '_percent_str' in d:
                    percent_str = d['_percent_str'].strip().replace('%', '')
                    try:
                        percent = float(percent_str)
                    except:
                        pass
                
                download_manager.add_download(download_id, {
                    **download_manager.get_download(download_id),
                    'progress': percent,
                    'speed': d.get('_speed_str', 'N/A'),
                    'eta': d.get('_eta_str', 'N/A')
                })
    
    def _format_duration(self, seconds):
        """Format duration in seconds to HH:MM:SS"""
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
        """Format file size in human readable format"""
        if not bytes_size:
            return "Unknown"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
    
    def _get_quality_display(self, fmt):
        """Get quality display string"""
        if fmt.get('height'):
            return f"{fmt['height']}p"
        elif fmt.get('format_note'):
            return fmt['format_note']
        elif fmt.get('ext') and fmt['acodec'] != 'none' and fmt['vcodec'] == 'none':
            return 'Audio'
        return fmt.get('ext', 'unknown').upper()
    
    def _get_audio_quality(self, fmt):
        """Get audio quality score"""
        quality_map = {
            'best': 100,
            '320': 90,
            '256': 80,
            '192': 70,
            '128': 60,
            '96': 50,
            '64': 40,
            '32': 30
        }
        
        format_note = fmt.get('format_note', '').lower()
        for key, score in quality_map.items():
            if key in format_note:
                return score
        return 50

# Initialize downloader
downloader = ProfessionalVideoDownloader()

# ==================== ROUTES ====================
@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'message': 'Professional Video Downloader API',
        'version': '2.0',
        'status': 'running',
        'supported_platforms': list(SUPPORTED_PLATFORMS.keys())
    })

@app.route('/api/info', methods=['POST'])
@limiter.limit("10 per minute")
def get_video_info():
    """Get video information"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not downloader.validate_url(url):
            return jsonify({'error': 'Unsupported platform or invalid URL'}), 400
        
        video_info = downloader.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
@limiter.limit("5 per minute")
def start_download():
    """Start video download"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best[height<=720]')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not downloader.validate_url(url):
            return jsonify({'error': 'Unsupported platform or invalid URL'}), 400
        
        # Generate download ID
        download_id = uuid.uuid4().hex
        
        # Start download in background
        def download_task():
            try:
                downloader.download_video(url, format_id, download_id)
            except Exception as e:
                logger.error(f"Background download failed: {e}")
        
        threading.Thread(target=download_task, daemon=True).start()
        
        return jsonify({
            'download_id': download_id,
            'status': 'started',
            'message': 'Download started in background'
        })
        
    except Exception as e:
        logger.error(f"Download start error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<download_id>/status')
def get_download_status(download_id):
    """Get download status"""
    try:
        download_data = download_manager.get_download(download_id)
        if not download_data:
            return jsonify({'error': 'Download not found'}), 404
        
        return jsonify({
            'download_id': download_id,
            'status': download_data.get('status'),
            'progress': download_data.get('progress', 0),
            'speed': download_data.get('speed'),
            'eta': download_data.get('eta'),
            'error': download_data.get('error')
        })
        
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<download_id>/file')
def get_downloaded_file(download_id):
    """Download the completed file"""
    try:
        download_data = download_manager.get_download(download_id)
        if not download_data:
            return jsonify({'error': 'Download not found'}), 404
        
        if download_data.get('status') != 'completed':
            return jsonify({'error': 'Download not completed'}), 400
        
        filepath = download_data.get('filepath')
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        filename = download_data.get('filename', 'download.mp4')
        
        # Determine MIME type
        if filename.endswith('.mp3'):
            mimetype = 'audio/mpeg'
        else:
            mimetype = 'video/mp4'
        
        response = send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
        # Schedule cleanup after 1 hour
        def cleanup():
            time.sleep(3600)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                download_manager.remove_download(download_id)
            except:
                pass
        
        threading.Thread(target=cleanup, daemon=True).start()
        
        return response
        
    except Exception as e:
        logger.error(f"File download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/supported-platforms')
def get_supported_platforms():
    """Get list of supported platforms"""
    return jsonify({
        'platforms': SUPPORTED_PLATFORMS,
        'count': len(SUPPORTED_PLATFORMS)
    })

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'service': 'Video Downloader API'
    })

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': 'File too large'}), 413

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded'}), 429

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# ==================== MAIN ====================
if __name__ == '__main__':
    logger.info("🚀 Starting Professional Video Downloader API")
    logger.info(f"📍 Port: {PORT}")
    logger.info(f"🔧 Debug: {DEBUG_MODE}")
    logger.info(f"📺 Supported platforms: {len(SUPPORTED_PLATFORMS)}")
    
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=DEBUG_MODE,
        threaded=True
    )
