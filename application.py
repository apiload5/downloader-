# main.py - FINAL BUG-FIXED, STABLE, AND CLOUD-READY VERSION

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging
import time

# Simple logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

SUPPORTED_PLATFORMS = [
    'youtube.com', 'youtu.be', 'facebook.com', 'fb.watch',
    'instagram.com', 'tiktok.com', 'twitter.com', 'x.com',
    'dailymotion.com'
]

# --- Cleanup function defined OUTSIDE the route ---
def cleanup_file(filepath):
    """Deletes the temporary file from the server's disk."""
    try:
        os.remove(filepath)
        logger.info(f"Cleaned up file: {filepath}")
    except Exception as e:
        logger.error(f"Error cleaning up file {filepath}: {e}")

class WorkingVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
        }
    
    def validate_url(self, url):
        """URL validation"""
        try:
            return any(platform in url.lower() for platform in SUPPORTED_PLATFORMS)
        except:
            return False
    
    def format_duration(self, seconds):
        if not seconds:
            return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def format_filesize(self, bytes_size):
        if not bytes_size:
            return "Unknown"
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
        elif fmt.get('ext') == 'm4a' and fmt.get('acodec') != 'none':
            return 'MP3'
        return fmt.get('ext', 'unknown').upper()
    
    def filter_and_sort_formats(self, formats):
        """Filter and sort formats: Only keep Muxed formats up to 720p."""
        
        valid_formats = []
        for f in formats:
            is_muxed = f['vcodec'] != 'none' and f['acodec'] != 'none'
            height = int(''.join(filter(str.isdigit, f['quality']))) if f['quality'].endswith('p') else 0

            # Only include Muxed MP4s up to 720p OR audio-only formats
            if (is_muxed and height <= 720 and f['ext'] == 'mp4') or (f['vcodec'] == 'none' and f['acodec'] != 'none'):
                 valid_formats.append(f)
        
        # Sort Logic: By resolution descending
        def get_sort_key(fmt):
            try:
                height = int(''.join(filter(str.isdigit, fmt['quality'])))
            except:
                height = 0
            return -height 
        
        # Remove duplicates
        seen = set()
        unique_formats = []
        for fmt in sorted(valid_formats, key=get_sort_key):
            key = (fmt['quality'], fmt['ext'])
            if key not in seen:
                seen.add(key)
                unique_formats.append(fmt)
                
        return unique_formats

    def get_video_info(self, url):
        """Get video information with stable formats up to 720p."""
        try:
            logger.info(f"Fetching info for: {url}")
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info: raise Exception("No video information found")
                
                thumbnail = info.get('thumbnail', '')
                video_data = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': thumbnail,
                    'formats': []
                }
                
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('ext') == 'None': continue
                        format_info = {
                            'format_id': fmt.get('format_id', ''),
                            'ext': fmt.get('ext', 'mp4'),
                            'quality': self.get_quality_display(fmt),
                            'filesize': self.format_filesize(fmt.get('filesize')),
                            'format_note': fmt.get('format_note', ''),
                            'vcodec': fmt.get('vcodec', 'none'),
                            'acodec': fmt.get('acodec', 'none')
                        }
                        formats.append(format_info)
                
                video_data['formats'] = self.filter_and_sort_formats(formats)
                
                # 1. Add Best 720p MP4 (Most stable video option)
                video_data['formats'].insert(0, {
                    'format_id': 'best_720p_mp4',
                    'ext': 'mp4',
                    'quality': 'Best Quality (720p MP4)',
                    'filesize': 'Varies',
                    'format_note': 'Video + Audio (Most Stable)',
                    'vcodec': 'muxed',
                    'acodec': 'muxed'
                })
                
                # 2. Add Best Audio MP3 (Requires FFmpeg)
                video_data['formats'].append({
                    'format_id': 'bestaudio',
                    'ext': 'mp3',
                    'quality': 'Best Audio (MP3)',
                    'filesize': 'Varies',
                    'format_note': 'Audio Only (FFmpeg Used)',
                    'vcodec': 'none',
                    'acodec': 'mp3'
                })
                
                return video_data
                
        except Exception as e:
            logger.error(f"Error in get_video_info: {str(e)}")
            raise Exception(f"Could not get video info: {str(e)}")
    
    def download_video(self, url, format_id, quality):
        """Download video with high stability using best Muxed format up to 720p."""
        temp_dir = tempfile.gettempdir()
        final_filepath = None
        
        filename_base = f"download_{uuid.uuid4().hex}"
        filepath_no_ext = os.path.join(temp_dir, filename_base)
        
        download_opts = {
            'outtmpl': filepath_no_ext + '.%(ext)s', 
            'quiet': False, 
            'no_warnings': False,
        }

        if format_id == 'bestaudio':
            format_str = 'bestaudio/best'
            download_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192', 
            }]
        
        elif format_id == 'best_720p_mp4':
            # This format string ensures MP4 is preferred and resolution is capped at 720p (muxed stream)
            format_str = 'best[height<=720][ext=mp4]/best[ext=mp4]/best'
        
        else:
            format_str = format_id

        download_opts['format'] = format_str

        try:
            logger.info(f"Attempting download for: {url} with format string: {format_str}")

            # Capture the list of files BEFORE download
            files_before = set(os.listdir(temp_dir))

            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])

            # Capture the list of files AFTER download
            files_after = set(os.listdir(temp_dir))
            new_files = files_after - files_before
            
            # Search for the file that starts with our unique base name
            for f in new_files:
                if f.startswith(filename_base):
                    final_filepath = os.path.join(temp_dir, f)
                    break
            
            if not final_filepath or not os.path.exists(final_filepath):
                raise Exception("CRITICAL ERROR: Final file not found after download. Check if FFmpeg is working for audio extraction/muxing.")
            
            file_size = os.path.getsize(final_filepath)
            if file_size == 0:
                os.remove(final_filepath)
                raise Exception("Empty file downloaded.")
            
            logger.info(f"Download successful: {final_filepath} ({file_size} bytes)")
            return final_filepath

        except Exception as e:
            logger.error(f"Download Error: {str(e)}")
            try:
                if final_filepath and os.path.exists(final_filepath):
                    os.remove(final_filepath)
            except:
                pass
            
            raise Exception(f"Download failed: {str(e)}. (Ensure FFmpeg is installed for MP3/Audio.)")

# Initialize downloader
downloader = WorkingVideoDownloader()

# Routes
@app.route('/api/info', methods=['POST'])
def get_video_info_route():
    try:
        data = request.get_json()
        if not data: return jsonify({'error': 'No data provided'}), 400
        url = data.get('url', '').strip()
        if not url: return jsonify({'error': 'URL is required'}), 400
        if not downloader.validate_url(url): return jsonify({'error': 'Unsupported platform'}), 400
        
        video_info = downloader.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        logger.error(f"Info error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video_route():
    """Download video and clean up the file after sending."""
    try:
        data = request.get_json()
        if not data: return jsonify({'error': 'No data provided'}), 400
            
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best_720p_mp4') 
        quality = data.get('quality', 'Best Quality (720p MP4)') 
        
        if not url: return jsonify({'error': 'URL is required'}), 400
        
        filepath = downloader.download_video(url, format_id, quality)
        
        _, file_ext = os.path.splitext(filepath)

        if format_id == 'bestaudio':
            filename = f"audio_download_{uuid.uuid4().hex}.mp3"
            mimetype = 'audio/mpeg'
        else:
            filename = f"video_download_{uuid.uuid4().hex}{file_ext}"
            mimetype = 'video/mp4'

        # --- FIX: Use Callback for Cleanup ---
        # The 'after_request' decorator is replaced by the 'on_close' callback
        # which is the correct way to handle cleanup after sending a file.
        response = send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
        # Attach the cleanup function to the response's close event
        response.call_on_close(lambda: cleanup_file(filepath))
        return response
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({'status': 'healthy', 'service': 'Video Downloader'})

@app.route('/')
def home():
    """Home page"""
    return jsonify({'message': 'Video Downloader API - Stable Version', 'status': 'Running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting STABLE Video Downloader...")
    app.run(host='0.0.0.0', port=port, debug=False)
