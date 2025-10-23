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

# --- AWS Elastic Beanstalk Configuration ---
# Beanstalk par, 'application' naam zaroori hai
application = Flask(__name__) 

# --- SECURITY CONFIGURATION: CORS ---
# Apne production domain se badal len
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com" 
CORS(application, origins=[ALLOWED_ORIGIN])
# ---

# --- Quality Configuration ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]

class UniversalDownloader:
    def __init__(self):
        # YDL options. ffmpeg_location yahan se hata diya gaya hai.
        # Kyunki Beanstalk FFmpeg ko system wide install karega (jise yt-dlp khud dhoond lega).
        self.ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'external_downloader_args': ['-movflags', 'faststart'],
            'postprocessors': [],
            # FFmpeg_location ko system path par chhod diya gaya hai (best practice for AWS)
        }
    
    # --- URL Validation and Search methods are UNCHANGED ---
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
                
                # --- Format Generation (Now relies on FFmpeg for merging) ---
                video_formats = []
                
                for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
                    
                    # COMPLEX FORMAT STRING FOR MERGING (Requires FFmpeg, which Beanstalk will install)
                    # This ensures high quality video and audio merging into MP4.
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
                        
                # 2. Audio Only (MP3 Conversion is now possible!)
                audio_format = {
                    'id': 'bestaudio_mp3_converted',
                    'name': 'Audio Only (MP3 - High Quality)',
                    'format_id': 'bestaudio/best', # Actual ytdlp audio format string
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
        """Download video/audio using system FFmpeg for merging and conversion"""
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
            
            # 1. Audio Conversion to MP3
            if is_audio_conversion:
                ydl_opts.update({
                    # Use FFmpeg system tool to convert to MP3
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192', 
                    }],
                    'outtmpl': os.path.join(temp_dir, filename_base + '.mp3'),
                })
            
            # 2. Video with Merging (FFmpeg required)
            else:
                # Ensures merged output is MP4
                ydl_opts['postprocessors'].append(
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                )
                ydl_opts['outtmpl'] = os.path.join(temp_dir, filename_base + '.mp4')
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # --- Find the final file ---
            download_ext = 'mp3' if is_audio_conversion else 'mp4'
            
            downloaded_file = None
            for f in os.listdir(temp_dir):
                if f.startswith(filename_base) and f.endswith(f'.{download_ext}'):
                    downloaded_file = os.path.join(temp_dir, f)
                    break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise Exception("Downloaded file not found. Check if FFmpeg installed correctly on the system.")

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
            # Specific error if FFmpeg dependency is missing
            if 'ffmpeg not found' in str(e) or 'FFmpeg' in str(e) and ('extract audio' in str(e) or 'merge' in str(e)):
                 raise Exception(f"Download failed: FFmpeg execution error. Check if the .ebextensions script installed FFmpeg correctly.")
            
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

@application.route('/')
def home():
    return jsonify({
        'message': 'Universal Downloader API (SaveFrom/Y2Mate Style)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'supported_sites': '1000+ sites (via yt-dlp)',
        'note': 'FFmpeg is installed via .ebextensions, so all qualities should now include audio.',
        'available_endpoints': ['/api/info', '/api/download', '/api/search']
    })

@application.route('/api/info', methods=['POST'])
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

@application.route('/api/download', methods=['POST'])
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
        if 'audio' in format_id:
            filename = "download.mp3"
            mimetype = 'audio/mpeg'
        else:
             # Use video title if available, otherwise generic
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
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        return jsonify({'error': str(e)}), 500

@application.route('/api/search', methods=['POST'])
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

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=os.environ.get('PORT', 8080), debug=True)
