#!/bin/bash
NAME="YetiAudioStream"

## Stream Identifier (URL of the Yeti, a.k.a. Soundcard 1 or 2)
STREAM="alsa://hw:2,0"

#### TODO: ^ Make dynamic (search `/proc/asound/cards`)

## Session Description File
SDP="sap"

## Destination Address (a multicast IP address)
DST="239.255.12.42"

#### TODO: ^ Read in destination address & port from a file

## Port must be an even number
PORT=1234

## Audio Codec
ACODEC="mp3"

## Bitrate
AB=128

## Audio Channels
AC=2

## Sampling Frequency (either 48000 Hz or 44100 Hz)
AR=48000


#### WORKING EXAMPLES:
#cvlc -vvv alsa://hw:1,0	--sout='#transcode{acodec=mp3,ab=128,channels=2,samplerate=48000}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name="YetiAudioStream"}' --sout-keep
#cvlc -vvv alsa://hw:Microphone	--sout='#transcode{acodec=aac,ab=128,channels=2,samplerate=44100}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name="YetiAudioStream"}' --sout-keep
#cvlc -vvv alsa://hw:Microphone	--sout='#transcode{acodec=aac,ab=64,aenc=ffmpeg,channels=1,samplerate=48000}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name="YetiAudioStream"}' --sout-keep
#cvlc -vvv alsa://hw:Microphone	--sout='#transcode{acodec=aac,ab=64,aenc=ffmpeg,channels=2,samplerate=48000}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name="YetiAudioStream"}' --sout-keep
#cvlc -vvv alsa://hw:Microphone	--sout='#transcode{acodec=aac,ab=128,aenc=ffmpeg,channels=2,samplerate=48000}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name="YetiAudioStream"}' --sout-keep



#### NON-WORKING EXPERIMENTAL OPTIONS:
#cvlc -vvv alsa://hw:Microphone --sout-keep --sout='#es{access=rtp,mux=ts,url_audio=239.255.12.42:1234}'
#cvlc -vvv alsa://hw:Microphone --sout-keep --sout='#transcode{acodec=mp3}:duplicate{dst=display{delay=6000},dst=gather:std{mux=ts,dst=239.255.12.42:1234,access=rtp},select="novideo"}'



# cvlc -vvv $STREAM --sout='#transcode{acodec=$ACODEC,ab=$AB,channels=$AC,samplerate=$AR}:rtp{mux=ts,dst=$DST,port=$PORT,sdp=$SDP,name="YetiAudioStream"}' --sout-keep

### These codecs are not recommended, as they require conversions from s16l --> f32l
#cvlc -vvv alsa://hw:Microphone --sout-keep --no-sout-video --sout='#transcode{acodec=a52,ab=128,aenc=ffmpeg,channels=2,samplerate=48000,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,proto=udp,name="YetiAudioStream"}'
#cvlc -vvv alsa://hw:Microphone --sout-keep --no-sout-video --sout='#transcode{acodec=mp4a,ab=128,aenc=ffmpeg,channels=2,samplerate=48000,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,proto=udp,name="YetiAudioStream"}'

#cvlc -vvv alsa://hw:Microphone --sout-keep --no-sout-video --sout='#transcode{acodec=mp3,ab=128,aenc=ffmpeg,channels=2,samplerate=48000,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,proto=udp,name="YetiAudioStream"}'
#cvlc -vvv alsa://hw:Microphone --sout-keep --no-sout-video --sout='#transcode{acodec=mpga,ab=128,aenc=ffmpeg,channels=2,samplerate=48000,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,proto=udp,name="YetiAudioStream"}'
cvlc -vvv alsa://hw:Microphone --sout-keep --no-sout-video --sout='#transcode{acodec=mpga,ab=128,channels=2,samplerate=48000,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,proto=udp,name="YetiAudioStream"}'
