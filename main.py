from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
import yt_dlp
import os
import tempfile
import uuid
import logging
import re
import shutil

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- SECURITY CONFIGURATION: CORS ---
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com"
CORS(app, origins=[ALLOWED_ORIGIN])
# ---

# --- Quality Configuration ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]

# --- FFmpeg Path: The path to the static binary we placed in the 'bin' folder ---
FFMPEG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'ffmpeg')

class UniversalDownloaderFixed:
    def __init__(self):
        # Now we tell yt-dlp where to find the external FFmpeg
        self.ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'external_downloader_args': ['-movflags', 'faststart'],
            # IMPORTANT: Set the path to the FFmpeg binary!
            'ffmpeg_location': FFMPEG_PATH 
        }
    
    # --- (Validation and Search methods remain UNCHANGED) ---
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
    
    def search_videos(self, query):
        """Search videos on YouTube using yt-dlp's search functionality"""
        try:
            if not query: return []
            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'quiet': True,
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
        try:
            logger.info(f"Fetching info for: {url}")
            
            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'quiet': True,
                'extract_flat': False,
            })
            
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
                
                # --- Format Generation Logic (Re-enabling Merging) ---
                video_formats = []
                
                for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
                    
                    # COMPLEX FORMAT STRING FOR MERGING (Requires FFmpeg)
                    # bestvideo[height<=H][ext=mp4] + bestaudio[ext=m4a]/best[height<=H]
                    format_string = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/{height}p/best[height<={height}]"
                    
                    custom_id = f'{height}p_mp4_merged'
                    
                    video_formats.append({
                        'id': custom_id,
                        # Now we can promise Video + Audio
                        'name': f'Video + Audio ({height}p MP4)', 
                        'format_id': format_string, 
                        'quality': f'{height}p',
                        'ext': 'mp4',
                        'size': 'Estimating...', # Size is hard to estimate before merging
                    })
                        
                # 2. Audio Only (MP3 Conversion is now possible!)
                audio_format = {
                    'id': 'bestaudio_mp3_converted',
                    'name': 'Audio Only (MP3 - High Quality)',
                    'format_id': 'bestaudio/best', # Use the actual ytdlp audio format string
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
        """Download video/audio using FFmpeg for merging and conversion"""
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
                'merge_output_format': 'mp4', # Default merge to MP4
            })
            
            # 1. Audio Conversion to MP3
            if is_audio_conversion:
                ydl_opts.update({
                    # Use FFmpeg to convert to MP3
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192', 
                    }],
                    'outtmpl': os.path.join(temp_dir, filename_base + '.mp3'),
                })
            
            # 2. Video with Merging (FFmpeg required)
            else:
                # Ensure the merge output is MP4
                ydl_opts['postprocessors'].append(
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                )
                ydl_opts['outtmpl'] = os.path.join(temp_dir, filename_base + '.mp4')
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # --- Find the final file ---
            download_ext = 'mp3' if is_audio_conversion else 'mp4'
            
            # Find the downloaded file based on the base name and expected extension
            downloaded_file = None
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base) and f.endswith(f'.{download_ext}'):
                    downloaded_file = os.path.join(temp_dir, f)
                    break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise Exception("Downloaded file not found. Check FFmpeg path and permissions.")

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
            # Provide an error if FFmpeg failed to run
            if 'ffprobe' in str(e) or 'ffmpeg' in str(e):
                 raise Exception(f"Download failed: FFmpeg execution error. Check if '{FFMPEG_PATH}' exists and has executable permission (chmod +x).")
            
            raise Exception(f"Download failed: {str(e)}")
            
    # --- Helper methods ---
    def _format_duration(self, seconds):
        if not seconds: return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

# Initialize downloader
downloader = UniversalDownloaderFixed()

# --- ROUTES (Remain the same) ---

@app.route('/')
def home():
    return jsonify({
        'message': 'Universal Downloader API (FFmpeg Static Binary)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'supported_sites': '1000+ sites (via yt-dlp)',
        'note': f'FFmpeg is integrated from: {FFMPEG_PATH}. All qualities should now include audio.',
        'available_endpoints': ['/api/info', '/api/download', '/api/search']
    })

# (Rest of the /api/info, /api/download, and /api/search routes remain UNCHANGED)

# --- (The route definitions are omitted for brevity but should be included in your final code) ---
if __name__ == '__main__':
    logger.info("🚀 Universal Downloader Started (FFmpeg Static Binary Mode)")
    # Check if the binary exists on startup
    if not os.path.exists(FFMPEG_PATH):
        logger.error(f"FATAL: FFmpeg binary not found at {FFMPEG_PATH}. Please follow step 1.")
    else:
        logger.info("FFmpeg binary found and integrated.")
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080), debug=True)
