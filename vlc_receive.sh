#!/bin/bash
USE_GUI=true  ## If set to false, will invoke with `cvlc` rather than `vlc`
if [ $# -gt 0 ]; then
	HOST=$1
else
	HOST="239.255.12.42"
fi
if [ $# -gt 1 ]; then
	PORT=$2
else
	PORT=1234
fi

case "$(uname)" in 
	"darwin") [[ $USE_GUI = true ]] && VLC_BIN="/Applications/VLC.app/Contents/MacOS/VLC" || VLC_BIN="/Applications/VLC.app/Contents/MacOS/VLC -I dummy" ;;
	# "Linux")
	*) [[ $USE_GUI = true ]] && VLC_BIN="vlc" || VLC_BIN="cvlc" ;;
esac

# if [ $(uname) = "Linux" ]; then
# 	if [ $USE_GUI = true ]; then
# 		VLC_BIN="vlc"
# 	else
# 		VLC_BIN="cvlc"
# 	fi
# else
# 	VLC_BIN="/Applications/VLC.app/Contents/MacOS/VLC"
# 	if [ $USE_GUI = false ]; then
# 		VLC_BIN="${VLC_BIN} -I dummy"
# 	fi
# fi

# if [ $USE_GUI = true ]; then
# 	vlc rtp://@${HOST}:${PORT}
# else
# 	cvlc rtp://@${HOST}:${PORT}
# fi

$VLC_BIN -vv rtp://@${HOST}:${PORT}