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
	"--sout=#transcode{acodec=%s,ab=%d,aenc=%s,channels=%d,samplerate=%d,threads=%d}:rtp{mux=ts,dst=%s,port=%d,sdp=%s,name=\"%s\"}" % (
		stream_data['acodec'],
		stream_data['bitrate'],
		stream_data['aencoder'],
		stream_data['channels'],
		stream_data['samplerate'],
		stream_data['threads'],
		stream_data['dest'],
		stream_data['port'],
		stream_data['sdp'],
		stream_data['name']
		)
]

cmd_str = "cvlc {} {} {}".format(opts[0], stream_data['mrl'], ' '.join(opts[1:]))
print(cmd_str, end="\n\n")

inst = vlc.Instance(opts)

"""
ret = inst.vlm_add_broadcast("YetiBroadcast", stream_data['mrl'], opts[-1].replace("--sout=",""), 3, opts[:2], 1, 0)
if ret >= 0:
	print("\n>>>>  vlm_add_broadcast() OKAY\n")
else:
	print("\n>>>>  vlm_add_broadcast() FAILED\n")
"""

p = inst.media_player_new()
p.set_mrl(stream_data['mrl'])
p.play()

while True:
	try:
		# p.play()
		pass
	except KeyboardInterrupt:
		break
p.stop()
