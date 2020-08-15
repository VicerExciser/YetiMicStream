#!/bin/bash

MIC=$(aplay -l | grep Yeti | cut -d ':' -f 2 | cut -d '[' -f 1 | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
SERVERIP=$(ip route get 8.8.8.8 | awk -F"src " 'NR==1{split($2,a," ");print a[1]}')
echo Server IP:  $SERVERIP
CLIENTIP=$(echo $SERVERIP | cut -d '.' -f 1-3).255  ## Broadcast to all on subnet/LAN
echo Client IP:  $CLIENTIP
PORT=5001

#arecord -f cd -D plughw:$MIC | ffmpeg -i - -acodec libmp3lame -ab 32k -ac 1 -re -f rtp rtp://$CLIENTIP:$PORT
#arecord -f cd -D plughw:$MIC | ffmpeg -i - -acodec libmp3lame -ab 32k -ac 1 -f rtp rtp://$CLIENTIP:$PORT

rm audio.sdp
arecord -f cd -D plughw:2,0 | ffmpeg -re -i - -c:a libmp3lame -ab 32k -ac 1 -f rtp rtp://234.5.5.5:1234
