from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
import yt_dlp
import os
import tempfile
import uuid
import logging
import re
import math 
import shutil # For safely handling file renaming across different file systems

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- SECURITY CONFIGURATION: CORS ---
# صرف اس ڈومین کو اجازت ہے
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com"
CORS(app, origins=[ALLOWED_ORIGIN])
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
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                ydl.extract_info(url, download=False, process=False)
                return True
        except:
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
                
                # --- Format Generation Logic (Fixed for No FFmpeg) ---
                
                video_formats = []
                # 1. Video + Audio (MP4) Formats
                for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
                    
                    # New Simplified Format String: Prioritizes combined streams
                    # 1. best[height<=H][ext=mp4] -> Looks for a single MP4 stream with audio (Works up to ~480p)
                    # 2. bestvideo[height<=H][ext=mp4] -> Fallback: Video Only stream
                    # We remove the merge string to avoid the explicit FFmpeg error.
                    format_string = f"best[height<={height}][ext=mp4]/{height}p/bestvideo[height<={height}][ext=mp4]"
                    
                    # We use a custom format ID that includes the height for front-end clarity
                    custom_id = f'{height}p_mp4'
                    
                    video_formats.append({
                        'id': custom_id,
                        'name': f'Video + Audio (Max {height}p MP4)',
                        'format_id': format_string, # Send the simple format string to download
                        'quality': f'{height}p',
                        'ext': 'mp4',
                        'size': 'Estimating...', 
                    })
                        
                # 2. Audio Only (MP3 Placeholder) Format
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
        temp_dir = tempfile.gettempdir()
        
        try:
            file_id = uuid.uuid4().hex
            filename_base = f"download_{file_id}"
            
            is_audio_download = (format_id == 'bestaudio/best')

            ydl_opts = {
                'outtmpl': os.path.join(temp_dir, filename_base + '.%(ext)s'),
                'format': format_id,
                'postprocessors': [],
                # IMPORTANT: Set merge_output_format to 'webm' to prevent unwanted FFmpeg merge calls
                'merge_output_format': 'webm', 
            }
            
            # 1. Audio-only download
            if is_audio_download:
                # We allow yt-dlp to download the file with its original extension (.m4a/.opus)
                pass 
            
            # 2. Video with Audio/Video Only
            else:
                # Force the output template to MP4 to ensure a consistent file name for later renaming/finding
                ydl_opts['outtmpl'] = os.path.join(temp_dir, filename_base + '.mp4')
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # --- Find and Rename Logic (Updated for stability) ---
            
            # Find the downloaded file based on the base name
            downloaded_file = None
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base) and not f.endswith('.part'):
                    downloaded_file = os.path.join(temp_dir, f)
                    break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise Exception("Downloaded file not found. Try a lower quality.")

            # Final file path and renaming logic
            filepath = downloaded_file
            
            if is_audio_download:
                # Rename the downloaded audio file (e.g., .m4a) to .mp3
                final_name = f"{filename_base}.mp3"
                final_path = os.path.join(temp_dir, final_name)
                # Use shutil.move for reliable rename across filesystems
                shutil.move(downloaded_file, final_path)
                filepath = final_path
            
            elif not downloaded_file.endswith('.mp4'):
                # Rename downloaded video (e.g., .webm) to .mp4 for consistency
                 final_name = f"{filename_base}.mp4"
                 final_path = os.path.join(temp_dir, final_name)
                 shutil.move(downloaded_file, final_path)
                 filepath = final_path


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
            # Clearer message on high-res failure due to no FFmpeg
            if 'bestvideo' in format_id and 'bestaudio' not in format_id:
                 raise Exception(f"Download failed (No Audio): For this high quality, the video stream contains no audio. You must use a tool like FFmpeg to combine the audio, or choose a 480p/360p option.")
            
            raise Exception(f"Video Download failed: {str(e)}")
            
    # --- Search Functionality (Same as before) ---
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
downloader = UniversalDownloaderFixed()

# --- ROUTES ---

@app.route('/')
def home():
    return jsonify({
        'message': 'Universal Downloader API (SaveFrom/Y2Mate Style)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'supported_sites': '1000+ sites (via yt-dlp)',
        'note': 'For 720p/1080p downloads, the video stream often lacks audio without FFmpeg.',
        'available_endpoints': ['/api/info', '/api/download', '/api/search']
    })

@app.route('/api/info', methods=['POST'])
@cross_origin(origins=[ALLOWED_ORIGIN])
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
@cross_origin(origins=[ALLOWED_ORIGIN])
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
@cross_origin(origins=[ALLOWED_ORIGIN])
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

# End of file mein yeh hona chahiye:
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)
