#!/bin/bash
# 02_set_permissions.sh
# FFmpeg binary ko execute karne ki ijazat dena

BIN_FILE="bin/ffmpeg"

echo "Setting execute permission for $BIN_FILE..."

# chmod +x command chalana
chmod +x $BIN_FILE

echo "Permission set completed."
