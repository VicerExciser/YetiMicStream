#!/bin/bash
## Script to playback all WAV files in current directory
for filename in $(ls)
do
	## Extract file extension from each filename
	ext=${filename##*\.}
	# echo "(filename = '${filename}', extension = '${ext}'"
	case "$ext" in
		wav) echo "Playing audio file:  '${filename}'" && omxplayer -o both $filename ;;
		mp3) echo "Playing audio file:  '${filename}'" && omxplayer -o both $filename ;;
		*) ;;
	esac
done