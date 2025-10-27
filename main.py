from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
import yt_dlp
import os
import tempfile
import uuid
import logging
import re
import shutil
import functools # Import for functools.wraps

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- SECURITY CONFIGURATION: CORS ---
# NOTE: Replace with your actual domain if you deploy this!
ALLOWED_ORIGIN = "https://crispy0921.blogspot.com"
# Allow CORS for the specified origin
CORS(app, origins=[ALLOWED_ORIGIN])
# ---

# --- Quality Configuration ---
ALLOWED_VIDEO_QUALITIES = [1080, 720, 480, 360, 240, 144]

# --- FFmpeg Path: The path to the static binary we placed in the 'bin' folder ---
# This assumes the 'bin/ffmpeg' file is in the same directory as this script.
FFMPEG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'ffmpeg')

# --- Helper for Temporary Directory Cleanup ---
def cleanup_file(filepath):
    """Helper function to safely remove a file."""
    if filepath and os.path.exists(filepath):
        try:
            # Check if it's not a directory and is a file before attempting to unlink
            if os.path.isfile(filepath):
                os.unlink(filepath)
                logger.info(f"Cleaned up file: {filepath}")
        except Exception as e:
            logger.error(f"Error cleaning up file {filepath}: {e}")

class UniversalDownloaderFixed:
    def __init__(self):
        # We tell yt-dlp where to find the external FFmpeg
        self.ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'external_downloader_args': ['-movflags', 'faststart'],
            # IMPORTANT: Set the path to the FFmpeg binary!
            'ffmpeg_location': FFMPEG_PATH 
        }
    
    def _format_duration(self, seconds):
        """Helper to format duration in seconds to M:SS format."""
        if not seconds or not isinstance(seconds, (int, float)): return "Unknown"
        minutes = int(seconds) // 60
        seconds = int(seconds) % 60
        return f"{minutes}:{seconds:02d}"

    def validate_url(self, url):
        """Validate if URL is supported by yt-dlp"""
        if not url or not isinstance(url, str):
            return False
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # Use download=False, process=False for a fast check
                ydl.extract_info(url, download=False, process=False)
                return True
        except:
            return False
    
    def search_videos(self, query):
        """Search videos on YouTube using yt-dlp's search functionality"""
        try:
            if not query: return []
            # Make a copy of ydl_opts to add search-specific options
            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'quiet': True,
                'default_search': 'ytsearch10', # Search and return up to 10 results
                'extract_flat': 'in_playlist',  # Get info quickly without downloading
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                results = []
                if info and 'entries' in info:
                    for entry in info['entries']:
                        # Skip entries that are None or lack essential info
                        if entry and entry.get('url') and entry.get('id'):
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
                'extract_flat': False, # Need full details for formats
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("Video not found or inaccessible")
                
                # Check for playlist/multi-entry (handle single video only for this API)
                if info.get('_type') == 'playlist' or 'entries' in info:
                    # For simplicity, extract the first entry if it's a playlist/multi-video
                    if 'entries' in info and info['entries']:
                         info = info['entries'][0]
                    # If it's a playlist without entries, raise an error
                    elif info.get('_type') == 'playlist':
                        raise Exception("Playlists are not supported. Please use a direct video URL.")
                
                video_data = {
                    'success': True,
                    'title': info.get('title', 'Unknown Title'),
                    'thumbnail': info.get('thumbnail', ''),
                    'extractor': info.get('extractor', 'Unknown Platform'),
                    'duration': self._format_duration(info.get('duration')),
                    'uploader': info.get('uploader', 'N/A'),
                    'formats': [],
                }
                
                video_formats = []
                
                # 1. Video + Audio Merged (Requires FFmpeg)
                for height in sorted(ALLOWED_VIDEO_QUALITIES, reverse=True):
                    
                    # FORMAT STRING: Use "bestvideo[height<=H][ext=mp4]+bestaudio[ext=m4a]" 
                    # If that fails, fallback to 'best[height<=H]' which might be single stream
                    format_string = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}]"
                    
                    # The format ID passed to the download route must be the raw format string
                    video_formats.append({
                        'id': f'{height}p_mp4_merged',
                        'name': f'Video + Audio ({height}p MP4)', 
                        'format_id': format_string, 
                        'quality': f'{height}p',
                        'ext': 'mp4',
                        'size': 'Estimating...', # Size is hard to estimate before merging
                    })
                        
                # 2. Audio Only (MP3 Conversion is now possible!)
                # NOTE: The 'format_id' here is what yt-dlp uses to SELECT the audio, 
                # but the download method handles the conversion to MP3 via postprocessor.
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
            # Re-raise a more descriptive error for the API response
            raise Exception(f"Could not fetch video info: {str(e)}")

    def download_video(self, url, format_id):
        """Download video/audio using FFmpeg for merging and conversion"""
        filepath = None
        temp_dir = tempfile.gettempdir()
        
        # Use a unique temporary directory to isolate files and ensure easier cleanup
        # This is a good practice to prevent conflicts in a shared temp directory.
        download_temp_dir = os.path.join(temp_dir, uuid.uuid4().hex)
        os.makedirs(download_temp_dir, exist_ok=True)
        
        try:
            filename_base = "media" # A generic base name for output file
            
            # Determine if we're doing audio conversion
            is_audio_conversion = ('bestaudio/best' in format_id or 'audio' in format_id)

            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'outtmpl': os.path.join(download_temp_dir, filename_base + '.%(ext)s'),
                'format': format_id,
                'postprocessors': [],
                'merge_output_format': 'mp4', 
            })
            
            # 1. Audio Conversion to MP3
            if is_audio_conversion:
                ydl_opts.update({
                    # Use FFmpeg to convert to MP3
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192', # High quality MP3
                    }],
                    # The outtmpl must match the postprocessor's output extension
                    'outtmpl': os.path.join(download_temp_dir, filename_base + '.mp3'),
                })
                download_ext = 'mp3'
            
            # 2. Video with Merging (FFmpeg required)
            else:
                # Ensure the merge output is MP4 (default)
                ydl_opts['postprocessors'].append(
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                )
                ydl_opts['outtmpl'] = os.path.join(download_temp_dir, filename_base + '.mp4')
                # Add postprocessor for 'faststart' if not using external_downloader_args
                # The external_downloader_args in __init__ already covers faststart, 
                # but adding a separate post-processor for clarity/robustness:
                ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': False})
                
                download_ext = 'mp4'
            
            logger.info(f"Starting download: {url} with format: {format_id}")
            
            # --- Perform Download ---
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # yt-dlp returns a status code. This might be useful for debugging.
                ydl.download([url])
            
            # --- Find the final file ---
            # yt-dlp might rename the file based on the video title.
            downloaded_file = None
            for f in os.listdir(download_temp_dir):
                # Look for any file with the expected extension
                if f.endswith(f'.{download_ext}'):
                    downloaded_file = os.path.join(download_temp_dir, f)
                    break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise Exception(f"Downloaded file not found in {download_temp_dir}. Check yt-dlp output.")

            filepath = downloaded_file
            if os.path.getsize(filepath) == 0:
                raise Exception("Downloaded file is empty (Zero size).")
            
            logger.info(f"Download completed: {filepath}")
            # Return the file path and the temporary directory for cleanup
            return filepath, download_temp_dir
            
        except Exception as e:
            # Cleanup the entire temporary directory in case of error
            try:
                shutil.rmtree(download_temp_dir)
            except:
                pass
            
            # Provide an error if FFmpeg failed to run
            if 'ffprobe' in str(e) or 'ffmpeg' in str(e):
                 # Log the path and permissions hint
                 logger.error(f"FFmpeg execution error path check: {FFMPEG_PATH}")
                 raise Exception(f"Download failed: FFmpeg execution error. Check if '{FFMPEG_PATH}' exists and has executable permission (chmod +x).")
            
            raise Exception(f"Download failed: {str(e)}")

# Initialize downloader
downloader = UniversalDownloaderFixed()

# --- ROUTES ---

@app.route('/')
def home():
    """Simple API status route."""
    return jsonify({
        'message': 'Universal Downloader API (FFmpeg Static Binary)',
        'status': 'running',
        'security': f'Only accessible from {ALLOWED_ORIGIN}',
        'supported_sites': '1000+ sites (via yt-dlp)',
        'note': f'FFmpeg is integrated from: {FFMPEG_PATH}. All video qualities now include audio via merging.',
        'available_endpoints': ['/api/info', '/api/download', '/api/search']
    })

# --- Error Handling Helper ---
# A common way to handle errors in routes is a decorator or a central handler.
def api_response(func):
    """Decorator to handle common API errors and return JSON responses."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error in {func.__name__}: {e}")
            status_code = 500
            # Custom error codes based on exception type can be added here
            if "not found" in str(e).lower() or "inaccessible" in str(e).lower():
                status_code = 404
            elif "invalid url" in str(e).lower():
                status_code = 400
            
            return jsonify({'success': False, 'error': str(e)}), status_code
    return wrapper

@app.route('/api/search', methods=['GET'])
@api_response
def api_search():
    """
    Search for videos based on a query.
    GET /api/search?q=<query>
    """
    query = request.args.get('q', '')
    if not query:
        return jsonify({'success': False, 'error': 'Query parameter "q" is required.'}), 400
    
    results = downloader.search_videos(query)
    
    return jsonify({
        'success': True,
        'query': query,
        'results': results
    })


@app.route('/api/info', methods=['GET'])
@api_response
def api_info():
    """
    Get video info and available download formats.
    GET /api/info?url=<video_url>
    """
    url = request.args.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'URL parameter is missing.'}), 400

    if not downloader.validate_url(url):
        return jsonify({'success': False, 'error': 'Invalid URL or unsupported site.'}), 400

    video_info = downloader.get_video_info(url)
    return jsonify(video_info)

@app.route('/api/download', methods=['GET'])
@api_response
@cross_origin(origins=[ALLOWED_ORIGIN]) # Re-apply CORS specifically to the download route for headers
def api_download():
    """
    Trigger the download of a specific format.
    GET /api/download?url=<video_url>&format_id=<format_string>
    """
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    if not url or not format_id:
        return jsonify({
            'success': False, 
            'error': 'Missing required parameters: url and format_id.'
        }), 400
        
    if not downloader.validate_url(url):
        return jsonify({'success': False, 'error': 'Invalid URL or unsupported site.'}), 400

    # The download function now returns the file path and the temp dir path
    filepath, temp_dir_path = downloader.download_video(url, format_id)
    
    # Extract original filename for the download header (optional, but nice)
    try:
        # A simple filename based on the video title (requires a separate info call, 
        # but to keep it simple, we use a generic name for now).
        # A better approach is to fetch info once and pass the title.
        file_ext = os.path.splitext(filepath)[1]
        
        # Use a more descriptive name for the file header
        info = downloader.get_video_info(url)
        title = info.get('title', 'video')
        # Sanitize title for filename
        safe_title = re.sub(r'[^\w\-_\. ]', '', title).replace(' ', '_')
        
        filename = f"{safe_title}{file_ext}"
        
    except Exception as e:
        logger.warning(f"Could not generate descriptive filename: {e}")
        filename = os.path.basename(filepath)
        
    # --- Send File and Clean Up ---
    
    # Use send_file with the as_attachment flag
    response = send_file(
        filepath, 
        mimetype='application/octet-stream', 
        as_attachment=True,
        download_name=filename # Use download_name instead of attachment_filename
    )

    # After sending the file, we must clean up the temporary files/directory.
    # We use the 'after_request' hook to ensure cleanup happens *after* the file is sent.
    @response.call_on_close
    def cleanup():
        # This will be called when the response stream is closed.
        cleanup_file(filepath) # Remove the file itself
        # Remove the entire temporary directory (best practice)
        try:
            shutil.rmtree(temp_dir_path)
            logger.info(f"Cleaned up temporary directory: {temp_dir_path}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory {temp_dir_path}: {e}")

    # For safety/redundancy, you could also add an after_request hook, 
    # but call_on_close is usually sufficient for cleaning up the downloaded file.
    
    # NOTE: send_file handles the file reading/streaming, but the cleanup is crucial!
    return response


if __name__ == '__main__':
    logger.info("🚀 Universal Downloader Started (FFmpeg Static Binary Mode)")
    # Check if the binary exists on startup
    if not os.path.exists(FFMPEG_PATH):
        logger.error(f"FATAL: FFmpeg binary not found at {FFMPEG_PATH}. Please follow the setup instructions (e.g., placing the binary in a 'bin' folder).")
    elif not os.access(FFMPEG_PATH, os.X_OK):
        logger.error(f"FATAL: FFmpeg binary at {FFMPEG_PATH} does not have executable permission. Please run: ")
        print("--------------------------------------------------")
        print(f"chmod +x {FFMPEG_PATH}")
        print("--------------------------------------------------")
    else:
        logger.info("FFmpeg binary found and integrated.")
    
    # You might want to remove debug=True in a production environment
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)
