#!/bin/bash
USE_GUI=true  ## If set to false, will invoke with `cvlc` rather than `vlc`

if [ $# -gt 0 ]; then
	HOST=$1
	if [ $# -gt 1 ]; then
		PORT=$2
	else
		PORT=1234
	fi
else
	HOST="239.255.12.42"
	PORT=1234
fi

## Currently only supports Linux & MacOS platforms
case "$(uname)" in 
	"darwin") [[ $USE_GUI = true ]] && VLC_BIN="/Applications/VLC.app/Contents/MacOS/VLC" || VLC_BIN="/Applications/VLC.app/Contents/MacOS/VLC -I dummy" ;;
	*) [[ $USE_GUI = true ]] && VLC_BIN="vlc" || VLC_BIN="cvlc" ;;
esac

$VLC_BIN -vv rtp://@${HOST}:${PORT}