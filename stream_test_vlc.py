import os
import vlc
import yaml

with open('stream_opts.yaml') as f:
	stream_data = yaml.load(f, Loader=yaml.FullLoader)


opts = [
	"-vvv",
	# stream_data['mrl'],
	"--sout-keep",
	"--no-sout-video",
	"--sout",
	"#transcode{acodec=%s,ab=%d,channels=%d,samplerate=%d,threads=%d}:rtp{mux=ts,dst=%s,port=%d,sdp=%s,name=\"%s\"}" % (
		stream_data['acodec'],
		stream_data['bitrate'],
		stream_data['channels'],
		stream_data['samplerate'],
		stream_data['threads'],
		stream_data['dest'],
		stream_data['port'],
		stream_data['sdp'],
		stream_data['name']
		)
]

cmd_str = "cvlc {} alsa://hw:Microphone {} {} {} {}".format(*opts)
print(cmd_str, end="\n\n")

inst = vlc.Instance(opts)
p = inst.media_player_new()
p.set_mrl(stream_data['mrl'])
p.play()

while True:
	try:
		pass
	except KeyboardInterrupt:
		break
p.stop()