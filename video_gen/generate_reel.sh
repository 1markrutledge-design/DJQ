#!/bin/bash
set -e

DIR="/Users/markrutledge/Documents/DjQueue/video_gen"
cd $DIR

# 0. Clean up old clips
rm -f clip*.mp4 transition.mp4 final_reel.mp4 concat.txt

# 1. Generate Ugly Clips (Cold/Desaturated)
# Clip 1: 1.5s, Zoom In
ffmpeg -y -loop 1 -i ugly1.png -t 1.5 -vf "zoompan=z='zoom+0.001':d=45:s=1080x1920,hue=s=0.4" -c:v libx264 -pix_fmt yuv420p clip1.mp4

# Clip 2: 1.5s, Zoom Out
ffmpeg -y -loop 1 -i ugly2.png -t 1.5 -vf "zoompan=z='1.1-0.001*on':d=45:s=1080x1920,hue=s=0.4" -c:v libx264 -pix_fmt yuv420p clip2.mp4

# Clip 3: 1s, Subtle Zoom In
ffmpeg -y -loop 1 -i ugly3.png -t 1.0 -vf "zoompan=z='zoom+0.0015':d=30:s=1080x1920,hue=s=0.4" -c:v libx264 -pix_fmt yuv420p clip3.mp4

# 2. Generate Transition (1s White/Gold Flash)
# We use Clip 3's last frame and Clip 4's first frame with a blend
ffmpeg -y -f lavfi -i color=c=white:s=1080x1920:d=1 -vf "fade=in:st=0:d=0.5,fade=out:st=0.5:d=0.5" -c:v libx264 transition.mp4

# 3. Generate Handsome Clips (Warm/Luxury)
# Clip 4: 3s, Smooth Zoom In
ffmpeg -y -loop 1 -i handsome1.png -t 3.0 -vf "zoompan=z='zoom+0.0005':d=90:s=1080x1920,eq=saturation=1.2:contrast=1.1:brightness=0.05" -c:v libx264 -pix_fmt yuv420p clip4.mp4

# Clip 5: 3s, Smooth Zoom Out
ffmpeg -y -loop 1 -i handsome2.png -t 3.0 -vf "zoompan=z='1.1-0.0005*on':d=90:s=1080x1920,eq=saturation=1.2:contrast=1.1:brightness=0.05" -c:v libx264 -pix_fmt yuv420p clip5.mp4

# 4. Concatenate
echo "file 'clip1.mp4'" > concat.txt
echo "file 'clip2.mp4'" >> concat.txt
echo "file 'clip3.mp4'" >> concat.txt
echo "file 'transition.mp4'" >> concat.txt
echo "file 'clip4.mp4'" >> concat.txt
echo "file 'clip5.mp4'" >> concat.txt

ffmpeg -y -f concat -safe 0 -i concat.txt -c copy final_reel.mp4
