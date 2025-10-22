#!/bin/bash
# 01_download_ffmpeg.sh
# FFmpeg Static Binary ko Download aur Extract karna

FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
FFMPEG_ARCHIVE="ffmpeg-static.tar.xz"
BIN_DIR="bin"

# 1. 'bin' directory banao
mkdir -p $BIN_DIR

# 2. FFmpeg archive download karo
echo "Downloading FFmpeg binary from $FFMPEG_URL..."
wget $FFMPEG_URL -O $BIN_DIR/$FFMPEG_ARCHIVE

# 3. Archive ko extract karke sirf 'ffmpeg' file nikaalo
echo "Extracting ffmpeg executable..."
tar -xf $BIN_DIR/$FFMPEG_ARCHIVE -C $BIN_DIR/ --strip-components=1 ffmpeg-*-amd64-static/ffmpeg

# 4. Download ki hui archive file delete kardo
echo "Cleaning up archive file..."
rm $BIN_DIR/$FFMPEG_ARCHIVE

echo "FFmpeg download and extraction completed."
