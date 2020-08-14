#!/bin/bash -e

######################################################################
##  Script for receiving an audio stream from RPi on local network  ##
######################################################################

RUN_IN_BACK=false

SERVERIP=rpi.local
echo Host IP:  $SERVERIP

## Command to receive audio on client computer:
RCV_CMD='gst-launch-1.0 -v udpsrc port=5001 caps="application/x-rtp" ! queue ! rtppcmudepay ! mulawdec ! audioconvert ! autoaudiosink sync=false' # &
echo -e "$RCV_CMD\n"
if [[ $RUN_IN_BACK = true ]]; then
	$RCV_CMD &
else
	$RCV_CMD
fi

## Command to receive video stream:
#gst-launch-1.0 -v tcpclientsrc host=$SERVERIP port=5000 ! gdpdepay ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false

## Kill background task (`$!` expands to the PID of the last process executed in the background)
if [[ $RUN_IN_BACK = true ]]; then
	kill $!
fi
