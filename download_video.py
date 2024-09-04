import sys
from pytube import YouTube
import requests  # For platforms where direct downloading can be done
# You may need other libraries for different platforms

def download_youtube(video_url):
    try:
        yt = YouTube(video_url)
        stream = yt.streams.get_highest_resolution()
        file_path = stream.download(output_path="downloads")
        print(file_path)  # Return file path
    except Exception as e:
        print(f"Error downloading from YouTube: {e}")
        sys.exit(1)

def download_facebook(video_url):
    try:
        # Implement Facebook video download logic
        print("Facebook download not implemented yet.")
        # Use any Python Facebook video downloader library or API call here.
    except Exception as e:
        print(f"Error downloading from Facebook: {e}")
        sys.exit(1)

def download_tiktok(video_url):
    try:
        # Implement TikTok video download logic
        print("TikTok download not implemented yet.")
        # Use TikTok downloader library or URL parsing logic here.
    except Exception as e:
        print(f"Error downloading from TikTok: {e}")
        sys.exit(1)

def download_dailymotion(video_url):
    try:
        # Implement Dailymotion video download logic
        print("Dailymotion download not implemented yet.")
        # Use Dailymotion downloader library or API call here.
    except Exception as e:
        print(f"Error downloading from Dailymotion: {e}")
        sys.exit(1)

def download_instagram(video_url):
    try:
        # Implement Instagram video download logic
        print("Instagram download not implemented yet.")
        # Use Instagram downloader library or URL parsing logic here.
    except Exception as e:
        print(f"Error downloading from Instagram: {e}")
        sys.exit(1)

def download_vimeo(video_url):
    try:
        # Implement Vimeo video download logic
        print("Vimeo download not implemented yet.")
        # Use Vimeo downloader library or API call here.
    except Exception as e:
        print(f"Error downloading from Vimeo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    video_url = sys.argv[1]
    platform = sys.argv[2].lower()

    if platform == 'youtube':
        download_youtube(video_url)
    elif platform == 'facebook':
        download_facebook(video_url)
    elif platform == 'tiktok':
        download_tiktok(video_url)
    elif platform == 'dailymotion':
        download_dailymotion(video_url)
    elif platform == 'instagram':
        download_instagram(video_url)
    elif platform == 'vimeo':
        download_vimeo(video_url)
    else:
        print("Platform not supported.")
        sys.exit(1)
