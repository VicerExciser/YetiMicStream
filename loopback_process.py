import os
import sys
import time
import signal
import psutil
import datetime as dt
import statistics as stat 
from dataclasses import dataclass

"""
To receive the audio stream from another machine, simply run the command:
	
			$  vlc rtp://@<stream IP address>:<stream port>
	e.g.,
			$  vlc -vv rtp://@239.255.12.42:1234
"""

def _get_timestamp():
	return '{}Z'.format(dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')) #.%f')[:-3])

# print(_get_timestamp())

def get_pids_for(p_name="VLC"):
	procs = [p.info for p in psutil.process_iter(attrs=['pid', 'name']) if p_name.lower() in p.info['name'].lower()]  # or p_name in p.info['name']]
	# return procs
	# print("\n{}".format(procs))
	return [p['pid'] for p in procs]

def kill_pid(pid, p_name=None):
	os.kill(pid, signal.SIGKILL)  ## https://docs.python.org/3/library/signal.html#module-signal
	if p_name is not None:
		if pid in get_pids_for(p_name=p_name):
			os.system("kill {}".format(pid))

def kill_all_vlc():
	for pid in get_pids_for(p_name="VLC"):
		kill_pid(pid, p_name="VLC")

def display_proc_cpu_usage(proc_dict):
	disp_format = "\n[ CPU ]\t'{}' CPU Utilization:\t{}%"
	disp_str = "".join([disp_format.format(k, v.cpu_percent()) for k,v in proc_dict.items()])
	print(disp_str, end="\n\n")

def get_yeti_name():
	try:
		device_name = [l[l.index('[')+1:l.index(']')].strip() for l in os.popen('cat /proc/asound/cards').read().split('\n') if 'Yeti' in l and '[' in l][0]
	except:
		device_name = 'Microphone'
	finally:
		return device_name

##=============================================================================

# stream_rtp_url = "239.255.12.42"
# stream_rtp_port = 1234
# loopback_url = "127.0.0.1"

##=============================================================================

@dataclass
class AudioSettings:
	mrl: str = "alsa://hw:Microphone" 	#"alsa://hw:2,0"
	codec: str = "mpga" 	#"s16l" 	#"mp3"
	channels: int = 2 	#1
	samplerate: int = 44100 	#48000
	bitrate: int = 128 	#256

##=============================================================================

class VLCAudioStream():
	def __init__(self, name, audio_settings, dest_ip_address, dest_port=1234, 
				loopback_addr='127.0.0.1', loopback_port=1234, loopback_name='loopback', 
				verbose_level=0, executable='cvlc', protocol='rtp'):
		## NOTE: Currently no support for any protocol other than RTP; in future, can add support for HTTP streams
		self.name = name 
		self.cfg = audio_settings 	 ## Must be an `AudioSettings` dataclass instance
		self.out_addr = dest_ip_address
		self.out_port = dest_port
		self.dup_out_addr = loopback_addr
		self.dup_out_port = loopback_port
		self.dup_out_name = loopback_name
		self.vlc = executable
		self.proto = protocol
		self.v_opt = '-{}'.format('v'*verbose_level) if verbose_level in range(1,4) else '-q'
		self.opt_str = f'{self.v_opt} --no-sout-video --sout-audio --ttl=1 --sout-keep'
		self.__pid = None

	@property
	def input_stream(self):
		return self.cfg.mrl 

	@property
	def transcode_str(self):
		self.__transcode_str = ''.join([
				"transcode{acodec=", self.cfg.codec, 
				",ab=", str(self.cfg.bitrate), 
				",aenc=ffmpeg,channels=", str(self.cfg.channels), 
				",samplerate=", str(self.cfg.samplerate),
				",threads=2}"
				])
		return self.__transcode_str

	@property
	def duplicate_str(self):
		destination1 = ''.join(["rtp{mux=ts,dst=", self.out_addr, 
				",port=", str(self.out_port), ",sdp=sap,name='", self.name, "'}"])
		destination2 = ''.join(["rtp{mux=ts,dst=", self.dup_out_addr, 
				",port=", str(self.dup_out_port), ",sdp=sap,name='", self.dup_out_name, "'}"])
		self.__duplicate_str = ''.join(["duplicate{dst=", destination1, ",dst=", destination2, "}"])
		return self.__duplicate_str
	
	@property
	def sout(self):
		self.__sout = f"#{self.transcode_str}:{self.duplicate_str}"
		return self.__sout

	@property
	def stream_cmd(self):
		self.__stream_cmd = f'{self.vlc} {self.opt_str} --sout "{self.sout}" {self.input_stream} &'
		return self.__stream_cmd

	@property
	def pid(self):
		if self.__pid is None:
			vlc_pids = get_pids_for(p_name="VLC")
			if len(vlc_pids) == 1:
				self.__pid = int(vlc_pids[0])
		return self.__pid
	

	def display_stream_command(self):
		print(self.stream_cmd)
	
	def start(self):
		os.system(self.stream_cmd)
		##TODO: Update state

	def stop(self):
		if self.pid is not None:
			os.kill(self.pid, signal.SIGKILL)
		else:
			os.system('pkill vlc')
		##TODO: Update state

##TODO: Additional methods for controlling stream, reading CPU usage, etc.

##=============================================================================

##TODO: Class for VLCAudioReceiver
class VLCAudioReceiver():


##=============================================================================

class YetiManager():
	def __init__(self, mic_number):
		self.microphone_number = mic_number
		self.stream_name = f"YetiAudioStream_{self.microphone_number}"
		self.__device_name = None
		self.vlc_exe = "cvlc" if sys.platform != "darwin" else "/Applications/VLC.app/Contents/MacOS/VLC -I dummy"

		self.calibration_duration = 31
		self.sampling_multiplier = 1.036
		self.file_duration = self.truncate(float(os.getenv('RECORDING_DURATION', '30')) * self.sampling_multiplier, 3)
		self.duration_update = True

		self.start_time = ''
		self.end_time = ''
		self.filename = None

		## TODO: Read these configuration values in from a file
		self.CODEC = "mpga"  #"s16l"
		self.CHANNELS = 2  #1
		self.SAMPLERATE = 44100  #48000
		self.BITRATE = 256  #128
		self.settings = AudioSettings(self.mrl, self.CODEC, self.CHANNELS, self.SAMPLERATE, self.BITRATE)

		## TODO: Read these configuration values in from a file
		self.stream_rtp_addr = "239.255.12.42"
		self.stream_rtp_port = 1234
		self.loopback_addr = "127.0.0.1" 	## <-- Address to listen on for stream audio processing/saving
		self.loopback_port = 1234
		self.loopback_name = f"loopback_{self.microphone_number}"
		self.stream = VLCAudioStream(self.stream_name, self.settings, self.stream_rtp_addr, dest_port=self.stream_rtp_port, 
				loopback_addr=self.loopback_addr, loopback_port=self.loopback_port, loopback_name=self.loopback_name,
				verbose_level=0, executable=self.vlc_exe, protocol='rtp')

		


	@property
	def device_name(self):
		if self.__device_name is None:
			try:
				self.__device_name = [l[l.index('[')+1:l.index(']')].strip() for l in os.popen('cat /proc/asound/cards').read().split('\n') if 'Yeti' in l and '[' in l][0]
			except:
				self.__device_name = 'Microphone'
		return self.__device_name

	@property
	def mrl(self):
		""" Returns the Media Resource Locator (MRL) for the Yeti mic to be used as an audio input with VLC. """
		self.__mrl = f"alsa://hw:{self.device_name}" if sys.platform != "darwin" else "qtsound://"
		return self.__mrl
	
	

##=============================================================================

input_mrl = "alsa://hw:{}".format(get_yeti_name()) if sys.platform != "darwin" else "qtsound://"
vlc_exec = "cvlc" if sys.platform != "darwin" else "/Applications/VLC.app/Contents/MacOS/VLC"
loopback = "127.0.0.1"
rtp_addr = "239.255.12.42"
rtp_port = str(1234)
stream_name = "YetiAudioStream"
clip_duration = 30  ## Seconds
samplerate = str(44100)  #str(48000)
acodec = "mpga"  #"s16l"
bitrate = str(256)  #str(128)  ## In kBit/s


## Using `ffmpeg` as the audio encoder and setting the `threads` parameter to 2 reduces CPU costs by ~30% (a nearly two-fold reduction)
transcode_str = "transcode{acodec="+acodec+",ab="+bitrate+",aenc=ffmpeg,channels=2,samplerate=44100,threads=2}"

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
	#'-v', 
	'-q',
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
print("\n>>>  Now launching background Streaming Process\n>>>  stream_cmd:  `{}`\n".format(stream_cmd))
kill_all_vlc()
os.system(stream_cmd)
# stream_proc_pid = int(os.popen("echo $!").read()) #[:-1])
vlc_pids = get_pids_for(p_name="VLC")
if len(vlc_pids) == 1:
	stream_proc_pid = int(vlc_pids[0])
else:
	stream_proc_pid = None
print("\n>>>  Background stream task PID:  {}\n\n".format(stream_proc_pid))
stream_proc = psutil.Process(stream_proc_pid)
stream_proc.cpu_percent(interval=1)

recv_url = "rtp://@{}:{}".format(loopback, rtp_port)
n = 0
recv_proc_pid = None
while True:
	try:
		print("\n{}".format("="*20))
		outfilename = os.path.join(os.getcwd(), "stream_capture{}.wav".format(n))
		print(">>>  Now capturing audio clip:  '{}'".format(outfilename))
		recv_str = "#"+transcode_str+":std{access=file,mux=wav,dst="+outfilename+"}"  #.format(transcode_str, outfilename)
		#recv_cmd = '{} -v --no-sout-video --sout-audio --ttl=1 --sout-keep --sout "{}" {} vlc://quit &'.format(vlc_exec, recv_str, recv_url)
		recv_cmd = '{} -q --no-sout-video --sout-audio --ttl=1 --sout-keep --sout "{}" {} vlc://quit &'.format(vlc_exec, recv_str, recv_url)
		print(">>>  recv_cmd:  `{}`\n".format(recv_cmd))
		start_time = time.time()
		os.system(recv_cmd)
		recv_proc_pid = None  #int(os.popen("echo $!").read()) #[:-1])
		for pid in get_pids_for(p_name="VLC"):
			if int(pid) != stream_proc_pid:
				recv_proc_pid = int(pid)
				break
		print("\n>>>  Background receiver task PID:  {}\n".format(recv_proc_pid))
		recv_proc = psutil.Process(recv_proc_pid)
		recv_proc.cpu_percent(interval=1)
		tx_cpu_record = []
		rx_cpu_record = []
		while (time.time() - start_time) <= (clip_duration + 1):
			time.sleep(0.1)
			# display_proc_cpu_usage({"Streaming Process" : stream_proc, "Receiving Process" : recv_proc})
			tx_cpu_record.append(stream_proc.cpu_percent())
			rx_cpu_record.append(recv_proc.cpu_percent())
		print("\n>>>  Clip captured:  '{}'\n>>>  Killing recv. process with PID:  {}".format(outfilename, recv_proc_pid))
		kill_pid(recv_proc_pid, p_name="VLC")
		print("\n[ CPU ]  Average CPU Utilization for Streaming Process:\t{:.1f}%  (Max = {}%, Min = {}%)".format(stat.mean(tx_cpu_record), max(tx_cpu_record), min(tx_cpu_record)))
		print("[ CPU ]  Average CPU Utilization for Receiving Process:\t{:.1f}%  (Max = {}%, Min = {}%)\n".format(stat.mean(rx_cpu_record), max(rx_cpu_record), min(rx_cpu_record)))
		print("="*20)
		n += 1
	except (KeyboardInterrupt, psutil.NoSuchProcess):
		break

kill_all_vlc()

print("\n>>>  {}:  DONE\n".format(__file__))

