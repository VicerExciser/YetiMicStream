#!/bin/python3
import os
import subprocess as sp 
import time

""" 	
FFMPEG CLI - Main Options  (https://ffmpeg.org/ffmpeg.html#Options)
	-f  fmt (input/output)
		Force input or output file format. The format is normally auto detected for input files 
		& guessed from the file extension for output files, so this option is not needed in most cases.
		Can view all supported formats (including devices) with command `ffmpeg -formats`

	-i  url (input)
		input file url

	-y  (global)
		Overwrite output files without asking.

	-n  (global)
		Do not overwrite output files, and exit immediately if a specified output file already exists.

	-c[:stream_specifier] codec (input/output,per-stream)
	-codec[:stream_specifier] codec (input/output,per-stream)
		Select an encoder (when used before an output file) or a decoder (when used before an input file) 
		for one or more streams. codec is the name of a decoder/encoder or a special value `copy` (output only) 
		to indicate that the stream is not to be re-encoded.
		Can view all codecs known to libavcodec with command `ffmpeg -codecs`
		Note that the term ’codec’ is used throughout this documentation as a shortcut for what is more correctly called a media bitstream format.

	-t duration (input/output)
		When used as an input option (before -i), limit the duration of data read from the input file.
		When used as an output option (before an output url), stop writing the output after its duration reaches duration.

	-fs limit_size (output)
		Set the file size limit, expressed in bytes. No further chunk of bytes is written after the limit is exceeded. 
		The size of the output file is slightly more than the requested file size.


	-itsoffset offset (input)
		Set the input time offset. The offset is added to the timestamps of the input files. 
		Specifying a positive offset means that the corresponding streams are delayed by the time duration specified in offset.
		

		Can view all supported protocols with command `ffmpeg -protocols`
		Can view all autodetected sources of input devices with command `ffmpeg -sources`
		Can view all autodetected sources of output devices with command `ffmpeg -sinks`

Audio Options
	-aframes number (output)
		Set the number of audio frames to output. This is an obsolete alias for -frames:a, which you should use instead.

	-ar[:stream_specifier] freq (input/output,per-stream)
		Set the audio sampling frequency. For output streams it is set by default to the frequency of the corresponding input stream. 
		For input streams this option only makes sense for audio grabbing devices and raw demuxers and is mapped to the corresponding demuxer options.

	-aq q (output)
		Set the audio quality (codec-specific, VBR). This is an alias for -q:a.

	-ac[:stream_specifier] channels (input/output,per-stream)
		Set the number of audio channels. For output streams it is set by default to the number of input audio channels. 
		For input streams this option only makes sense for audio grabbing devices and raw demuxers and is mapped to the corresponding demuxer options.

	-an (input/output)
		As an input option, blocks all audio streams of a file from being filtered or being automatically selected or mapped for any output. 
		See -discard option to disable streams individually.
		As an output option, disables audio recording i.e. automatic selection or mapping of any audio stream. 
		For full manual control see the -map option.

	-acodec codec (input/output)
		Set the audio codec. This is an alias for -codec:a.

	-sample_fmt[:stream_specifier] sample_fmt (output,per-stream)
		Set the audio sample format. Use -sample_fmts to get a list of supported sample formats.

	-af filtergraph (output)
		Create the filtergraph specified by filtergraph and use it to filter the stream. This is an alias for -filter:a, see the -filter option.

Advanced Options (https://ffmpeg.org/ffmpeg.html#Advanced-options)
	-map [-]input_file_id[:stream_specifier][?][,sync_file_id[:stream_specifier]] | [linklabel] (output)
		Designate one or more input streams as a source for the output file. Each input stream is identified by the input file index input_file_id and 
		the input stream index input_stream_id within the input file. Both indices start at 0. 
		If specified, sync_file_id:stream_specifier sets which input stream is used as a presentation sync reference.

		The first -map option on the command line specifies the source for output stream 0, the second -map option specifies the source for output stream 1, etc.
		A trailing ? after the stream index will allow the map to be optional: if the map matches no streams the map will be ignored instead of failing. 
		Note the map will still fail if an invalid input file index is used; such as if the map refers to a non-existent input.

		For example, to map ALL streams from the first input file to output:
						`ffmpeg -i INPUT -map 0 output`
		
		For example, if you have two audio streams in the first input file, these streams are identified by "0:0" and "0:1". 
		You can use -map to select which streams to place in an output file. 
		For example:
						`ffmpeg -i INPUT -map 0:1 out.wav`
		will map the input stream in INPUT identified by "0:1" to the (single) output stream in out.wav.

		To map the video and audio streams from the first input, and using the trailing ?, ignore the audio mapping if no audio streams exist in the first input:
						`ffmpeg -i INPUT -map 0:v -map 0:a? OUTPUT`


	-re (input)
		Read input at native frame rate. Mainly used to simulate a grab device, or live input stream (e.g. when reading from a file). 
		Should not be used with actual grab devices or live input streams (where it can cause packet loss). 
		By default ffmpeg attempts to read the input(s) as fast as possible. 
		This option will slow down the reading of the input(s) to the native frame rate of the input(s). 
		It is useful for real-time output (e.g. live streaming).
_______________________________________________________________________________________________________________________________________
## Lossy codec options:         [AAC, MP3, Opus, Vorbis, Speex, G.711, AC3]; 
## Lossless codec options:      [FLAC]; 
## Uncompressed format options: [WAV, AIFF, DSD, PCM]

## Descriptions of & more details on the best audio formats & codecs for streaming: 
## 	- wowza.com/blog/best-audio-codecs-live-streaming#AAC
## 	- adobe.com/creativecloud/video/discover/best-audio-format.html
"""

server_ip = "239.0.0.1"  #"127.0.0.1"  #  #"172.20.10.2"  ## 239.0.0.1 is a multicast address
server_port = 1234 #5004  #
output_format = "rtp"
stream_target = f"{output_format}://{server_ip}:{server_port}"
output_file_ext = "m4a"  ## M4A == MP4

mic_name = "hw:2,0"  #"hw:Microphone"  #"hwplug:Microphone"  ## <-- Sound card 2 (/proc/asound/Microphone/ or /proc/asound/card2/)
audio_format = "alsa"  #"mp3" #"wav"  ## <-- .wav files use AAC (libfdk_aac)
auto_detect_format = False #True
audio_codec = "aac"  #"libfdk_aac"  #"libmp3lame"  ## Or use "-c:a copy" to just mux the audio source into the output without re-encoding ("stream copied")
skip_reencoding = False

audio_channels = 2  #1
bit_rate = str(64 * audio_channels)+"k"  #"128k"  #"32k" 	## As a rule of thumb, use 64 kBit/s for each channel (so 128 kBit/s for stero, 384 kBit/s for 5.1 surround sound)
constant_bitrate_mode = True  #False  ## Variable Bit Rate (`vbr`) mode is apparently a video stream setting
use_native_framerate = True

audio_sampling_frequency = 48000  #44100  #8000
delay_offset = 0  #5.5
inlcude_offset = False 
include_fflags = False
include_strict = False
include_mappings = False

opts = {
			"input" : f"-i {mic_name}",
			"in_format" : f"-f {audio_format}" if not auto_detect_format else "",
			"codec" : f"-acodec {audio_codec}" if not skip_reencoding else "-c:a copy",
			"channels" : f"-ac {audio_channels}",
			"frequency" : f"-ar {audio_sampling_frequency}",
			"framerate" : "-re" if use_native_framerate else "",
			"bitrate" : f"-b:a {bit_rate}" if constant_bitrate_mode else "-vbr 3",
			"delay" : f"-itsoffset {delay_offset}" if inlcude_offset else "",
			"flags" : "-fflags nobuffer" if include_fflags else "",  ## The `nobuffer` option reduces the latency introduced by buffering during intitial input streams analysis
			"strict" : "-strict experimental" if include_strict else "",   ## See: superuser.com/questions/543589/information-about-ffmpeg-command-line-options
			"mapping" : "-map 0:0 -map 1:0" if include_mappings else "",
			"out_format" : f"-f {output_format}",
			"target" : f"{stream_target}"
}

"""
Input #0, alsa, from 'hw:2,0':
  Duration: N/A, start: 1597447917.618509, bitrate: 1536 kb/s
    Stream #0:0: Audio: pcm_s16le, 48000 Hz, stereo, s16, 1536 kb/s
Stream mapping:
  Stream #0:0 -> #0:0 (pcm_s16le (native) -> aac (native))

Output #0, rtp, to 'rtp://172.20.10.2:1234':
  Metadata:
    encoder         : Lavf58.20.100
    Stream #0:0: Audio: aac (LC), 44100 Hz, stereo, fltp, 128 kb/s
    Metadata:
      encoder         : Lavc58.35.100 aac
"""

## FFMPEG Command format:  ffmpeg [input options] -i input_url [output options] output_url

#stream_cmd = f"ffmpeg {opts['framerate']} {opts['in_format']} {opts['delay']} {opts['flags']} {opts['input']} {opts['codec']} {opts['channels']} {opts['frequency']} {opts['bitrate']} {opts['mapping']} {opts['strict']} {opts['out_format']} {opts['target']}"

## e.g.,       ffmpeg -f mp3 -i sender.mp3 -c:a libmp3lame -b:a 128k -ac 2 -ar 44100 -re -f rtp rtp://172.20.10.2:1234
# stream_cmd = f"ffmpeg {opts['in_format']} {opts['input']} {opts['codec']} {opts['bitrate']} {opts['channels']} {opts['frequency']} -re {opts['out_format']} {opts['target']}"

sdp_file = os.path.join(os.getcwd(), "audio.sdp")

def get_stream_cmd(need_sdp_gen=True):
    #stream_cmd = "ffmpeg -re -f alsa -i hw:2,0 -c:a copy {}"  #rtp://172.20.10.2:5004" ## Use '-re' for live streams
    stream_cmd = "ffmpeg -re -f alsa -fflags nobuffer -i hw:2 -c:a aac {}"  ## <-- SUCCESS! (when receiving via `ffplay -protocol_whitelist file,rtp,udp -i audio.sdp`)
    #stream_cmd = 'ffmpeg -re -f lavfi -i aevalsrc="sin(400*2*PI*t)" -ar 8000 -f mulaw {}'
    ## ^^ This works! Receive with command:  gst-launch-1.0 -v udpsrc port=1234 caps="application/x-rtp" ! queue ! rtppcmudepay ! mulawdec ! audioconvert ! autoaudiosink sync=false
    if need_sdp_gen:
        return stream_cmd.format(f"{opts['out_format']} -sdp_file {sdp_file} {opts['target']} &")
    return stream_cmd.format(f"{opts['out_format']} {opts['target']}")

#print(stream_cmd, end="\n\n")
if os.path.isfile(sdp_file):
    os.remove(sdp_file)
os.system(get_stream_cmd(need_sdp_gen=True))
time.sleep(1)
#os.system("kill $!")
os.system("sudo pkill ffmpeg")
os.system("sed -i '/^SDP:/d' audio.sdp")  ## Remove superfluous 'SDP:' line in audio.sdp
time.sleep(3)
#stream_cmd = "ffmpeg -re -f alsa -i hw:2,0 -c:a copy -f rtp {}".format(stream_target)  #rtp://172.20.10.2:5004"
stream_pipe = sp.Popen(get_stream_cmd(need_sdp_gen=False), shell=True, stdin=sp.PIPE)

try:
	now = time.strftime("%Y-%m-%d-%H:%M:%S")
	print(f"Start:  {now}")
	while True:
		## ... Pass microphone data to stream_pipe.stdin ?
		time.sleep(0.001)
except KeyboardInterrupt:
	now = time.strftime("%Y-%m-%d-%H:%M:%S")
	print(f"Interrupted:  {now}")
finally:
	stream_pipe.stdin.close()
	print("Good bye.")

