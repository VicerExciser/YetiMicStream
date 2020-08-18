import vlc
import time
import os

instance = vlc.Instance()
player = instance.media_player_new()

mrl = "alsa://hw:Microphone"
options = [mrl, "sout=#transcode{acodec=mpga,ab=256,channels=2,samplerate=48000,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap}", "sout-keep", "no-sout-video"]
media = instance.media_new(*options)


cmd = "cvlc -vvv {} --{} --{} --{}".format(*options)
os.system(cmd)


player.set_media(media)
player.play()

while True:
	try:
		pass
	finally:
		player.stop()
