#!/bin/bash -e
############################################################
##  Audio streaming script to be run on the Raspberry Pi  ##
############################################################

RUN_IN_BACK=false

DEVNAME=$(aplay -l | grep Yeti | cut -d':' -f2 | cut -d'[' -f1 | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
echo Device Name:  $DEVNAME

#SERVERIP=$(ifconfig | grep -E 'inet.[0-9]' | grep -v '127.0.0.1' | awk '{ print $2 }')
SERVERIP=$(ip route get 8.8.8.8 | awk -F"src " 'NR==1{split($2,a," ");print a[1]}')
echo Server IP:  $SERVERIP

CLIENTIP=$(echo $SERVERIP | cut -d '.' -f 1-3).255  ## Broadcast to all on subnet/LAN
echo Client IP:  $CLIENTIP

## Command to stream the audio:
STREAM_CMD="gst-launch-1.0 -v alsasrc device=plughw:$DEVNAME ! mulawenc ! rtppcmupay ! udpsink host=$CLIENTIP port=5001" # &
echo -e "$STREAM_CMD\n"
if [[ $RUN_IN_BACK = true ]]; then
	$STREAM_CMD &
else
	$STREAM_CMD
fi

## Command to stream video as well (from a raspicam):
#raspivid -t 999999 -w 1080 -h 720 -fps 25 -hf -b 2000000 -o - | gst-launch-1.0 -v fdsrc ! h264parse ! rtph264pay config-interval=1 pt=96 ! gdppay ! tcpserversink host=$SERVERIP port=5000

## Kill the last spawned background task (`$!` expands to the PID of the last process executed in the background)
if [[ $RUN_IN_BACK = true ]]; then
	#echo $!
	kill $!
fi
