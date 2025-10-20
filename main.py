# main.py - FINAL PROFESSIONAL AND CLOUD-READY VERSION
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
import logging

# Simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

SUPPORTED_PLATFORMS = [
    'youtube.com', 'youtu.be', 
    'facebook.com', 'fb.watch',
    'instagram.com',
    'tiktok.com',
    'twitter.com', 'x.com',
    'dailymotion.com'
]

class WorkingVideoDownloader:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,           # Quiet mode for clean logs
            'no_warnings': True,
            'ignoreerrors': True,
        }
    
    def validate_url(self, url):
        """URL validation"""
        try:
            return any(platform in url.lower() for platform in SUPPORTED_PLATFORMS)
        except:
            return False
    
    def get_video_info(self, url):
        """Get video information with all available formats and merged options"""
        try:
            logger.info(f"Fetching info for: {url}")
            
            # --- Fetch Info ---
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("No video information found")
                
                # ... (Thumbnail and basic info extraction remains the same) ...
                thumbnail = info.get('thumbnail', '')
                if not thumbnail and 'thumbnails' in info:
                    thumbnails = info['thumbnails']
                    if thumbnails:
                        thumbnail = thumbnails[-1].get('url', '') 
                
                video_data = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': thumbnail,
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'formats': []
                }
                
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('ext') == 'None' or not (fmt.get('vcodec') or fmt.get('acodec')):
                            continue
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
                
                # Filter and sort formats
                video_data['formats'] = self.filter_and_sort_formats(formats)
                
                # --- Requirement Fulfillment: Add Merged Formats ---
                # 1. Best Merged MP4 (Highest Quality Video + Audio)
                video_data['formats'].insert(0, {
                    'format_id': 'best_merged_mp4',
                    'ext': 'mp4',
                    'quality': 'Best Quality (MP4 - Merged)',
                    'filesize': 'Varies',
                    'format_note': 'Video + Audio (FFmpeg Used)',
                    'vcodec': 'merged',
                    'acodec': 'merged'
                })
                
                # 2. Best Audio MP3 (Audio Only)
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
    
    def filter_and_sort_formats(self, formats):
        """Filter and sort formats properly: Prioritize combined streams, then resolution."""
        # Keep only formats with video or audio
        valid_formats = [f for f in formats if f['vcodec'] != 'none' or f['acodec'] != 'none']
        
        def get_sort_key(fmt):
            has_both = 1 if fmt['vcodec'] != 'none' and fmt['acodec'] != 'none' else 0
            try:
                # Use height for sorting resolution
                height = int(''.join(filter(str.isdigit, fmt['quality'])))
            except:
                height = 0
            
            # Sort order: 1. Combined stream (highest priority), 2. Highest resolution
            return (-has_both, -height) 
        
        return sorted(valid_formats, key=get_sort_key)
    
    def download_video(self, url, format_id, quality):
        """Download video using FFmpeg for high-quality merging and extraction."""
        final_filepath = None
        temp_dir = tempfile.gettempdir()
        download_opts = {}
        
        try:
            logger.info(f"Downloading: {url} with format {format_id}")
            
            # --- CRITICAL FIX: Use Unique Base Name ---
            # This unique prefix is used to find the final file regardless of yt-dlp's final extension (.mp4, .mkv, etc.)
            filename_base = f"download_{uuid.uuid4().hex}"
            filepath_no_ext = os.path.join(temp_dir, filename_base)
            
            if format_id == 'bestaudio':
                # FFmpeg for MP3 extraction
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
                # FFmpeg for Video+Audio Merging (High Quality)
                download_opts = {
                    'outtmpl': filepath_no_ext + '.%(ext)s', 
                    # Use bestvideo and bestaudio, merged into mp4
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                }
                
            else:
                # Specific format download (e.g., 360p or a specific video-only stream)
                download_opts = {
                    'outtmpl': filepath_no_ext + '.%(ext)s',
                    'format': format_id or 'best[height<=720]',
                }

            download_opts.update({
                'quiet': False, 
                'no_warnings': False,
            })
            
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])
            
                # --- CRITICAL FIX: Search Temp Directory for Final File ---
                # This fixes the "Download failed - final file not found" error.
                files = os.listdir(temp_dir)
                for f in files:
                    if f.startswith(filename_base) and (f.endswith('.mp4') or f.endswith('.mp3')):
                        final_filepath = os.path.join(temp_dir, f)
                        break

            # Verify download
            if not final_filepath or not os.path.exists(final_filepath):
                # The detailed error explanation is handled in the final response section.
                raise Exception("Download failed - final file not found. Merging might have failed (FFmpeg issue).")
            
            file_size = os.path.getsize(final_filepath)
            if file_size == 0:
                os.remove(final_filepath)
                raise Exception("Download failed - empty file")
            
            logger.info(f"Download successful: {final_filepath} ({file_size} bytes)")
            return final_filepath
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            try:
                if final_filepath and os.path.exists(final_filepath):
                    os.remove(final_filepath)
            except:
                pass
            raise Exception(f"Download failed: {str(e)}")

    def format_duration(self, seconds):
        """Format duration"""
        if not seconds:
            return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def format_filesize(self, bytes_size):
        """Format file size"""
        if not bytes_size:
            return "Unknown"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
    
    def get_quality_display(self, fmt):
        """Get quality display"""
        if fmt.get('height'):
            return f"{fmt['height']}p"
        elif fmt.get('format_note'):
            return fmt['format_note']
        elif fmt.get('ext') == 'm4a' and fmt.get('acodec') != 'none':
            return 'MP3'
        return fmt.get('ext', 'unknown').upper()

# Initialize downloader
downloader = WorkingVideoDownloader()

# Routes
@app.route('/api/info', methods=['POST'])
def get_video_info_route():
    # ... (Info route remains the same) ...
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not downloader.validate_url(url):
            return jsonify({'error': 'Unsupported platform'}), 400
        
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
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best_merged_mp4') 
        quality = data.get('quality', 'Best Quality (MP4 - Merged)') 
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        filepath = downloader.download_video(url, format_id, quality)
        
        # Determine filename and extension based on the actual downloaded file
        _, file_ext = os.path.splitext(filepath)

        if 'audio' in quality.lower() or format_id == 'bestaudio':
            filename = f"audio_download_{uuid.uuid4().hex}{file_ext}"
            mimetype = 'audio/mpeg'
        else:
            filename = f"video_download_{uuid.uuid4().hex}{file_ext}"
            mimetype = 'video/mp4'

        # --- CRITICAL FIX: Cleanup Hook for Professional Deployment ---
        # This function ensures that the temporary file is deleted immediately after Flask sends it to the user.
        @app.after_request
        def cleanup(response):
            try:
                os.remove(filepath)
                logger.info(f"Cleaned up file: {filepath}")
            except Exception as e:
                logger.error(f"Error cleaning up file {filepath}: {e}")
            return response

        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'Video Downloader',
        'timestamp': '2024-01-15T10:00:00'
    })

@app.route('/')
def home():
    """Home page"""
    return jsonify({
        'message': 'Video Downloader API - Working Version',
        'status': 'Running'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting WORKING Video Downloader...")
    print(f"📍 Port: {port}")
    print("✅ Server starting...")
    app.run(host='0.0.0.0', port=port, debug=False)
