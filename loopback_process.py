import os
import sys
import time
import signal
import psutil
import datetime as dt

"""
To receive the audio stream from another machine, simply run the command:
	
			$  vlc rtp://@<stream IP address>:<stream port>
	e.g.,
			$  vlc rtp://@239.255.12.42:1234
"""

def _get_timestamp():
	return '{}Z'.format(dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')) #.%f')[:-3])

print(_get_timestamp())

def get_pids_for(p_name="VLC"):
	procs = [p.info for p in psutil.process_iter(attrs=['pid', 'name']) if p_name in p.info['name']]
	# return procs
	print(procs)
	return [p['pid'] for p in procs]

def kill_pid(pid, p_name=None):
	os.kill(pid, signal.SIGKILL)  ## https://docs.python.org/3/library/signal.html#module-signal
	if p_name is not None:
		if pid in get_pids_for(p_name=p_name):
			os.system("kill {}".format(pid))

def kill_all_vlc():
	for pid in get_pids_for(p_name="VLC"):
		kill_pid(pid, p_name="VLC")


input_mrl = "alsa://hw:Microphone" if sys.platform != "darwin" else "qtsound://"
vlc_exec = "vlc" if sys.platform != "darwin" else "/Applications/VLC.app/Contents/MacOS/VLC"
loopback = "127.0.0.1"
rtp_addr = "239.255.12.42"
rtp_port = str(1234)
stream_name = "YetiAudioStream"
acodec = "mpga"  #"s16l"
clip_duration = 30  ## Seconds


transcode_str = "transcode{acodec="+acodec+",channels=2}" #.format(acodec)
rtp_strf = "rtp{mux=ts,dst={},port={},sdp=sap,name='{}'}"
dup_dsts = [
	# rtp_strf.format(rtp_addr, rtp_port, stream_name),
	"rtp{mux=ts,dst="+rtp_addr+",port="+rtp_port+",sdp=sap,name='"+stream_name+"'}",
	# "std{access=file,mux=wav,dst={}}".format(loopback),
	# rtp_strf.format(loopback, rtp_port, "loopback")
	"rtp{mux=ts,dst="+loopback+",port="+rtp_port+",sdp=sap,name='loopback'}"
]
duplicate_str = "duplicate{dst="+dup_dsts[0]+",dst="+dup_dsts[1]+"}"  #.format(*dup_dsts)
sout_str = "#{}:{}".format(transcode_str, duplicate_str)
stream_opts = [
	'-v', 
	'-I', 'dummy',
	'--no-sout-video', 
	'--sout-audio', 
	'--ttl=1',
	'--sout-keep',
	'--sout',
	'"{}"'.format(sout_str),
	input_mrl,
	# 'vlc://quit',	## Likely unnecessary for the live stream
	'&'
]
stream_cmd = "{} {}".format(vlc_exec, ' '.join(stream_opts))
print("\n>>>  stream_cmd:  `{}`\n".format(stream_cmd))
kill_all_vlc()
os.system(stream_cmd)
# stream_proc_pid = int(os.popen("echo $!").read()) #[:-1])
vlc_pids = get_pids_for(p_name="VLC")
if len(vlc_pids) == 1:
	stream_proc_pid = int(vlc_pids[0])
else:
	stream_proc_pid = None
print("\n>>>  Background stream task PID:  {}\n".format(stream_proc_pid))


recv_url = "rtp://@{}:{}".format(loopback, rtp_port)
n = 0
recv_proc_pid = None
while True:
	try:
		outfilename = os.path.join(os.getcwd(), "stream_capture{}.wav".format(n))
		recv_str = "#"+transcode_str+":std{access=file,mux=wav,dst="+outfilename+"}"  #.format(transcode_str, outfilename)
		recv_cmd = '{} -v --no-sout-video --sout-audio --ttl=1 --sout-keep --sout "{}" {} vlc://quit &'.format(vlc_exec, recv_str, recv_url)
		print("\n>>>  recv_cmd:  `{}`\n".format(recv_cmd))
		start_time = time.time()
		os.system(recv_cmd)
		recv_proc_pid = None  #int(os.popen("echo $!").read()) #[:-1])
		for pid in get_pids_for(p_name="VLC"):
			if int(pid) != stream_proc_pid:
				recv_proc_pid = int(pid)
				break
		print("\n>>>  Background receiver task PID:  {}\n".format(recv_proc_pid))
		while (time.time() - start_time) <= (clip_duration + 1):
			time.sleep(0.1)
		print("\n>>>  Clip captured:  '{}'\n>>>  Killing recv. process with PID:  {}\n".format(outfilename, recv_proc_pid))
		kill_pid(recv_proc_pid, p_name="VLC")
		n += 1
	except KeyboardInterrupt:
		break

kill_all_vlc()

print("\n>>>  {}:  DONE\n".format(__file__))

