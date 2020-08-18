#!/bin/bash

####################
##  This program will live stream audio to an RTP address while 
##  saving 30-second audio captures into WAV files simultaneously
##  (NOTE: This results in the live feed being very briefly interrupted between each recording)
##
##  (POSSIBLE IMPROVEMENT: Dual stream -- 1 to RTP address, another to loopback/localhost,
##	implement a listener on localhost & process audio from that stream into WAV files)
####################

INPUT="alsa://hw:Microphone"
DEST="127.0.0.1" #"239.255.12.42"
DURATION=30 	### In seconds -- the length of the audio captures
NUM=0

if [ $(uname) = "Linux" ]; then
	CMD="vlc"
else
	### Account for testing on MacOS
	CMD="/Applications/VLC.app/Contents/MacOS/VLC"
	INPUT="qtsound://" 		### <-- MRL of the built-in microphone input
fi
echo $CMD

### The `s16l` codec is the audio codec for WAV format audio.
### Parameter `mux=wav` tells VLC to write the s16l audio data into a file with the WAV structure
AC="mpga" #"s16l"

while [ $NUM -le 10 ]; do
	OUTPUT="${PWD}/capture${NUM}.wav"
	end=$((SECONDS+DURATION)) 	### Capture audio stream in 30-second intervals
	echo $end
	echo -e "\n>>> BEGINNING AUDIO CAPTURE FOR FILE:  ${OUTPUT}\n"

	# vlc -I dummy --no-sout-video --sout-audio --sout-keep --sout "#transcode{acodec=s16l,channels=2}:std{access=file,mux=wav,dst=$OUTPUT}" $INPUT
	$CMD -v -I dummy --no-sout-video --sout-audio --ttl=1 --sout-keep --sout "#transcode{acodec=$AC,channels=2}:duplicate{dst=rtp{mux=ts,dst=$DEST,port=1234,sdp=sap,name='YetiAudioStream'},dst=std{access=file,mux=wav,dst=$OUTPUT}}" $INPUT vlc://quit &
	# cvlc --no-sout-video --sout-audio --sout-keep --sout "#transcode{acodec=s16l,channels=2}:duplicate{dst=rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name='YetiAudioStream'},dst=std{access=file,mux=wav,dst=$OUTPUT}}" $INPUT


	while [ $SECONDS -le $end ]; do
		sleep 1s
	done
	kill $!

	echo -e "\n>>> AUDIO FILE SAVED:  ${OUTPUT}\n"
	((NUM++))
done
echo -e "\n>>> DONE\n"