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
if [ $USE_GUI = true ]; then
	vlc rtp://@$HOST:$PORT
else
	cvlc rtp://@$HOST:$PORT
fi

