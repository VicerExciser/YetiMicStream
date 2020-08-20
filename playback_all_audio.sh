#!/bin/bash
## Script to playback all WAV files in current directory
for filename in $(ls)
do
	## Extract file extension from each filename
	ext=${filename##*\.}
	# echo "(filename = '${filename}', extension = '${ext}'"
	case "$ext" in
		wav | mp3) echo -e "\nPlaying audio file:  '${filename}'" && omxplayer -o both $filename ;;
		*) ;;
	esac
done
