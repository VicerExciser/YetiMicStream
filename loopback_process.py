import os
import sys
import time
import signal
# import psutil
import datetime as dt
import statistics as stat 
from dataclasses import dataclass
import subprocess
import shlex
from multiprocessing import Queue, Process

"""
To receive the audio stream from another machine, simply run the command:
	
			$  vlc rtp://@<stream IP address>:<stream port>
	e.g.,
			$  vlc -vv rtp://@239.255.12.42:1234
"""

def _get_timestamp():
	return '{}Z'.format(dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')) #.%f')[:-3])

# print(_get_timestamp())

def truncate(f, n):
	"""Truncates/pads a float f to n decimal places without rounding"""
	s = '{}'.format(f)
	if 'e' in s or 'E' in s:
		return '{0:.{1}f}'.format(f, n)
	i, p, d = s.partition('.')
	return float('.'.join([i, (d + '0' * n)[:n]]))

"""
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
"""

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
class VLCAudioSettings:
	tx_mrl: str = "alsa://hw:Microphone"   #"alsa://hw:2,0"
	rx_mrl: str = "rtp://@127.0.0.1:1234"
	codec: str = "mpga"                    #"s16l" 	#"mp3"
	channels: int = 2                      #1
	samplerate: int = 44100                #48000
	bitrate: int = 128                     #256

##=============================================================================

class VLCAudioBase():
	def __init__(self, name, audio_settings, verbose_level, executable, protocol):
		assert isinstance(audio_settings, VLCAudioSettings)
		self.name = name
		self.cfg = audio_settings 	 ## Must be an `AudioSettings` dataclass instance
		self.v_opt = '-{}'.format('v'*verbose_level) if verbose_level in range(1,4) else '-q'
		self.vlc = executable
		self.proto = protocol
		self.process = None
		self.__state = "STOPPED"

	@property
	def state(self):
		return self.__state

	@property
	def opt_str(self):
		return f'{self.v_opt} --no-sout-video --sout-audio --ttl=1 --sout-keep'
	
	@property
	def input_stream(self):
		if isinstance(self, VLCAudioStreamer):
			return self.cfg.tx_mrl
		elif isinstance(self, VLCAudioListener):
			return self.cfg.rx_mrl
		return "vlc://quit" 

	@property
	def transcode_str(self):
		## Alternatively, could make this a method within the VLCAudioSettings dataclass 
		return ''.join([
				"transcode{acodec=", self.cfg.codec, 
				",ab=", str(self.cfg.bitrate), 
				",aenc=ffmpeg,channels=", str(self.cfg.channels), 
				",samplerate=", str(self.cfg.samplerate),
				",threads=2}"
				])
	
	@property
	def pid(self):
		return self.process.pid if self.process else None

	@property
	def is_running(self):
		if self.process is None:
			if self.__state != "STOPPED":
				self.update_state("STOPPED")
			return False
		running = self.process.poll() is None 	## Popen.poll() returns the exit code of child process if it has terminated, else None
		if running and self.__state != "STREAMING":
			self.update_state("STREAMING")
		elif not running and self.__state != "STOPPED":
			self.update_state("STOPPED")
			## TODO: Should `self.process` be set to None here??
			# self.process = None
		return running 

	def update_state(self, new_state):
		if new_state != self.__state:
			self.__state = new_state
			print(f"\n[update_state::{self.name}]  NEW STATE: {new_state}")

	def update_audio_settings(self, new_settings):
		self.cfg = new_settings 	 ## Must be an `AudioSettings` dataclass instance

	


##=============================================================================

class VLCAudioStreamer(VLCAudioBase):
	def __init__(self, name, audio_settings, dest_ip_address, dest_port=1234, 
				loopback_addr='127.0.0.1', loopback_port=1234, loopback_name='loopback', 
				verbose_level=0, executable='cvlc', protocol='rtp'):
		## NOTE: Currently no support for any protocol other than RTP; in future, can add support for HTTP streams
		# self.name = name 
		super().__init__(name, audio_settings, verbose_level, executable, protocol)
		# self.cfg = audio_settings 	 ## Must be an `AudioSettings` dataclass instance
		self.out_addr = dest_ip_address
		self.out_port = dest_port
		self.dup_out_addr = loopback_addr
		self.dup_out_port = loopback_port
		self.dup_out_name = loopback_name
		# self.vlc = executable
		# self.proto = protocol
		# self.v_opt = '-{}'.format('v'*verbose_level) if verbose_level in range(1,4) else '-q'
		# self.opt_str = f'{self.v_opt} --no-sout-video --sout-audio --ttl=1 --sout-keep'

		# self.__state = "STOPPED"
		# self.process = None
	"""
	@property
	def state(self):
		return self.__state
	"""
	@property
	def duplicate_str(self):
		destination1 = ''.join(["rtp{mux=ts,dst=", self.out_addr, ",port=", str(self.out_port), ",sdp=sap,name='", self.name, "'}"])
		destination2 = ''.join(["rtp{mux=ts,dst=", self.dup_out_addr, ",port=", str(self.dup_out_port), ",sdp=sap,name='", self.dup_out_name, "'}"])
		return ''.join(["duplicate{dst=", destination1, ",dst=", destination2, "}"])
	
	@property
	def sout(self):
		return f"#{self.transcode_str}:{self.duplicate_str}"

	@property
	def stream_cmd(self):
		self.__stream_cmd = f'{self.vlc} {self.opt_str} --sout "{self.sout}" {self.input_stream} &'
		return self.__stream_cmd
	"""
	@property
	def pid(self):
		return self.process.pid if self.process else None
	"""
	"""
	@property
	def is_running(self):
		if self.process is None:
			if self.__state != "STOPPED":
				self.update_state("STOPPED")
			return False
		running = self.process.poll() is None 	## Popen.poll() returns the exit code of child process if it has terminated, else None
		if running and self.__state != "STREAMING":
			self.update_state("STREAMING")
		elif not running and self.__state != "STOPPED":
			self.update_state("STOPPED")
			## TODO: Should `self.process` be set to None here??
			# self.process = None
		return running 
	"""
	def display_stream_command(self):
		print(f"\n[{self.name}]  Stream Command: {self.stream_cmd}")
		print(f"\n[{self.name}]  Stream Command (split): {shlex.split(self.stream_cmd)}\n")

	# def update_state(self, new_state):
	# 	if new_state != self.__state:
	# 		self.__state = new_state
	# 		print(f"\n[update_state]  NEW STATE: {new_state}")

	def stream_start(self, use_shlex=True, use_shell=True): 	## Working arg combos: (use_shlex=False, use_shell=True), (use_shlex=True, use_shell=True)
		if not self.is_running:
			cmd = self.stream_cmd if not use_shlex else shlex.split(self.stream_cmd)
			self.process = subprocess.Popen(cmd, shell=use_shell)
			self.update_state("STREAMING")

	def stream_stop(self, redundant_kill=False):
		if self.process:
			self.process.kill()
			if redundant_kill:
				try:
					os.kill(self.pid, signal.SIGKILL)	## DON'T call os.kill() for pid -1!!
				except (ProcessLookupError, TypeError):
					pass
			while self.is_running:
				print(f"[stream_stop]  Waiting for child process '{self.name}' to terminate...")
				time.sleep(0.2)
				continue
			self.process = None
		self.update_state("STOPPED")
		

##TODO: Additional methods for controlling stream, reading CPU usage, etc.

##=============================================================================

##TODO: Class for VLCAudioListener
### cvlc -q --no-sout-video --sout-audio --ttl=1 --sout-keep \
### --sout "#transcode{acodec=mpga,ab=256,aenc=ffmpeg,channels=2,samplerate=44100,threads=2}:std{access=file,mux=wav,dst=output.wav}" \
### rtp://@127.0.0.1:1234 vlc://quit &
class VLCAudioListener(VLCAudioBase):
	def __init__(self, name, audio_settings, capture_format='wav', capture_duration=30, 
									verbose_level=0, executable='cvlc', protocol='rtp'):
		super().__init__(name, audio_settings, verbose_level, executable, protocol)
		self.clip_format = capture_format.lower()
		# self.clip_ext = f".{self.clip_format}"
		self.clip_len = capture_duration
		self.unprocessed_clips = Queue()  # list()

	@property
	def clip_filename(self):
		## TODO: Perhaps just return f"output.{self.clip_format}" without performing any checks for filename collisions
		clip_num = 0
		while f"output{clip_num}.{self.clip_format}" in (os.listdir()):  # + list(self.unprocessed_clips)):
			clip_num += 1
		self.__current_clip_name = f"output{clip_num}.{self.clip_format}"  # os.path.join(os.getcwd(), f"output{clip_num}.{self.clip_format}")
		# return self.__current_clip_name
		return os.path.join(os.getcwd(), self.__current_clip_name)
	
	@property
	def save_clip_str(self):
		return ''.join(["std{access=file,mux=", self.clip_format, ",dst=", self.clip_filename, "}"])
	
	@property
	def sout(self):
		return f"#{self.transcode_str}:{self.save_clip_str}"

	@property
	def listen_cmd(self):
		self.__listen_cmd = f'{self.vlc} {self.opt_str} --sout "{self.sout}" {self.input_stream} vlc://quit &'
		return self.__listen_cmd

	def display_listen_command(self):
		print(f"\n[{self.name}]  Listen Command: {self.listen_cmd}")
		print(f"\n[{self.name}]  Listen Command (split): {shlex.split(self.listen_cmd)}\n")

	def listen_start(self, use_shlex=True, use_shell=True):
		if not self.is_running:
			cmd = self.listen_cmd if not use_shlex else shlex.split(self.listen_cmd)
			print(f"[listen_start]  Listener '{self.name}' recording new clip:  '{self.__current_clip_name}'")
			# self.unprocessed_clips.append(self.__current_clip_name)
			self.unprocessed_clips.put(self.__current_clip_name)
			self.process = subprocess.Popen(cmd, shell=use_shell)
			self.update_state("RECORDING")
		else:
			print(f"[listen_start]  Listener '{self.name}' is already recording loopback audio; call ignored.")

	def listen_stop(self, redundant_kill=False):
		if self.process:
			self.process.kill()
			if redundant_kill:
				try:
					os.kill(self.pid, signal.SIGKILL)	## DON'T call os.kill() for pid -1!!
				except (ProcessLookupError, TypeError):
					pass
			while self.is_running:
				print(f"[listen_stop]  Waiting for child process '{self.name}' to terminate...")
				time.sleep(0.2)
				continue
			print(f"[listen_stop]  Listener '{self.name}' successfully captured audio clip:  '{self.__current_clip_name}'")
			self.__current_clip_name = None
			self.process = None
		else:
			print(f"[listen_stop]  Popen process for Listener '{self.name}' is None!")
		self.update_state("STOPPED")

	### TODO: ^ Abstract the process stop/kill method out into the VLCAudioBase class, as it's really the same for both the Streamer & Listener objects

	"""
	def register_file_as_processed(self, filename):
		if filename in self.unprocessed_clips:
			self.unprocessed_clips.remove(filename)
	"""

##=============================================================================

class YetiManager():
	def __init__(self, mic_number):
		self.microphone_number = mic_number
		self.stream_name = f"YetiAudioStream_{self.microphone_number}"
		self.listener_name = f"YetiAudioListener_{self.microphone_number}"
		self.__device_name = None
		self.vlc_exe = "cvlc" if sys.platform != "darwin" else "/Applications/VLC.app/Contents/MacOS/VLC -I dummy"

		self.calibration_duration = 31
		self.sampling_multiplier = 1.036
		self.file_duration = truncate(float(os.getenv('RECORDING_DURATION', '30')) * self.sampling_multiplier, 3)
		self.duration_update = True

		self.start_time = ''
		self.end_time = ''
		self.filename = None

		## TODO: Read these configuration values in from a file
		self.stream_rtp_addr = "239.255.12.42"
		self.stream_rtp_port = 1234
		self.loopback_addr = "127.0.0.1" 	## <-- Address to listen on for stream audio processing/saving
		self.loopback_port = 1234
		self.loopback_name = f"loopback_{self.microphone_number}"
		self.recording_format = "wav"
		self.verbose_level = 0  	## 0 = -q, 1 = -v, 2 = -vv, 3 = -vvv
		self.streaming_protocol = "rtp"

		## TODO: Read these configuration values in from a file
		self.CODEC = "mpga"  #"s16l"
		self.CHANNELS = 2  #1
		self.SAMPLERATE = 44100  #48000
		self.BITRATE = 256  #128
		self.settings = VLCAudioSettings(self.stream_mrl, self.loop_mrl, self.CODEC, self.CHANNELS, self.SAMPLERATE, self.BITRATE)


		self.streamer = VLCAudioStreamer(self.stream_name, self.settings, self.stream_rtp_addr, dest_port=self.stream_rtp_port, 
				loopback_addr=self.loopback_addr, loopback_port=self.loopback_port, loopback_name=self.loopback_name,
				verbose_level=self.verbose_level, executable=self.vlc_exe, protocol=self.streaming_protocol)
		## For DEBUG:
		self.streamer.display_stream_command()

		self.listener = VLCAudioListener(self.listener_name, self.settings, 
				capture_format=self.recording_format, capture_duration=self.file_duration, 
				verbose_level=self.verbose_level, executable=self.vlc_exe, protocol=self.streaming_protocol)
		## For DEBUG:
		self.listener.display_listen_command()


		## Multiprocessing queues
		self.post_queue = Queue()
		self.hash_queue = Queue()
		# self.frame_q = Queue()
		# self.kafka_hash_q = Queue()  # Needed since producers cannot be shared across processes

		## Processes
		print(f'[{self.__class__}]  Initializing Audio Process')
		self.audio_process = Process(target=self.audio_processing_loop, args=(self.hash_queue,))   # args=(self.frame_q, self.p, self.duration_lock, self.do_calibration_flag, self.calibration_lock))
	   
		print(f'[{self.__class__}]  Initializing Hash Process')
		self.hash_process = Process(target=self.hash_rename, args=(self.hash_queue, self.post_queue))

		print(f'[{self.__class__}]  Initializing Posting Process')
		self.posting_process = Process(target=self.post_cdn, args=(self.post_queue,))  # , self.kafka_hash_q))

		## Set all process daemons
		print(f'[{self.__class__}]  Setting all processes to daemon=True')
		self.audio_process.daemon = True
		self.hash_process.daemon = True
		self.posting_process.daemon = True


	@property
	def device_name(self):
		if self.__device_name is None:
			try:
				self.__device_name = [l[l.index('[')+1:l.index(']')].strip() for l in os.popen('cat /proc/asound/cards').read().split('\n') if 'Yeti' in l and '[' in l][0]
			except:
				self.__device_name = 'Microphone'
		return self.__device_name

	@property
	def stream_mrl(self):
		""" Returns the Media Resource Locator (MRL) for the Yeti mic to be used as an audio input with VLC. """
		return f"alsa://hw:{self.device_name}" if sys.platform != "darwin" else "qtsound://"

	@property
	def loop_mrl(self):
		return f"rtp://@{self.loopback_addr}:{self.loopback_port}"
	
	def audio_processing_loop(self, hash_q):
		print('Audio Process Successfully Started')
		self.streamer.stream_start()
		while True:
		# try:
			start_time = _get_timestamp()
			ts = time.time()
			self.listener.listen_start()
			while (time.time() - ts) <= int(self.listener.clip_len + 1):
				time.sleep(0.1)
			self.listener.listen_stop()
			end_time = _get_timestamp()
			## TODO: Use queue instead & ensure that all unprocessed_clips are processed & removed
			# audio_clip = self.hash_rename(self.listener.unprocessed_clips[0])
			audio_clip_name = self.listener.unprocessed_clips.get()  #[0]
			hash_q.put((audio_clip_name, start_time, end_time))
			# self.add_to_post_q(audio_clip)
			## Clear the start and end timestamps
			# self.start_time = ''
			# self.end_time = ''
			# except KeyboardInterrupt:
			# 	break
		
	def kill_all_vlc(self):
		print(f"\n[{self.__class__}]  Aborting: Terminating all VLC activities.")
		self.listener.listen_stop()
		self.streamer.stream_stop()
	
	def hash_rename(self, hash_q, post_q):  #old_filename):
		print('Hash Process Successfully Started')
		while True:
			while not hash_q.empty():
				# try:
				unprocessed_data = hash_q.get()
				old_filename = unprocessed_data[0]
				self.start_time = unprocessed_data[1]
				self.end_time = unprocessed_data[2]
				with open(old_filename, 'rb') as f:
					audio_data = f.read()
					h = hashlib.new('sha1', audio_data)
					new_filename = h.hexdigest() + f".{self.recording_format}"  # self.listener.clip_format}"
				os.rename(old_filename, new_filename)
				print(f"[hash_rename]  Audio file '{old_filename}' has been renamed to '{new_filename}'")
				# self.listener.register_file_as_processed(old_filename)
				# return new_filename

				filesize = os.path.getsize(new_filename)
				## Put all the data into the posting queue as a dictionary for easy unpacking
				post_q.put({
					"filename": new_filename,
					"file_size": filesize,
					"sha": new_filename.split('.')[0],
					"start_t": self.start_time,
					"end_t": self.end_time,
					# "calibration": calibration_flag
					})

				## Clear the start and end timestamps
				self.start_time = ''
				self.end_time = ''
				
	"""
	def add_to_post_q(self, filename):
		filesize = os.path.getsize(filename)
		# put all the data into the posting queue as a dictionary for easy unpacking
		# self.post_queue.put({
		post_queue.put({
			"filename": filename,
			"file_size": filesize,
			"sha": filename.split('.')[0],
			"start_t": self.start_time,
			"end_t": self.end_time,
			# "calibration": calibration_flag
			})
	"""

	def post_cdn(self, post_q):
		print('Posting Process Successfully Started')
		while True:
			while not post_q.empty():
				message = post_q.get()
				## Get the associated info from the message
				# calibration_flag = message["calibration"]
				filename = message["filename"]
				filesize = message["file_size"]
				sha = message["sha"]
				start_time = message["start_t"]
				end_time = message["end_t"]

				print(f"[MOCK::post_to_cdn]  Posting data to CDN: {message}")
				time.sleep(1)
				print(f"[MOCK::post_to_cdn]  Post to CDN was successful --> removing file '{filename}'")
				os.remove(filename)
				"""
				try:
					files = {'files': open(filename, 'rb')}
					response = requests.post(f'http://{cdn_url}:{cdn_port}/upload', files=files)
					fileid = response.text.split()[-1]

					# Ensure SHA posted matches the current file's SHA
					if fileid != sha:
						self.my_logger.error(f'SHA mismatch error!: file:{sha}, POST:{fileid}')
					confirmation = requests.get(f'http://{cdn_url}:{cdn_port}/{fileid}')
					if str(confirmation.status_code) != '200':
						self.my_logger.error(f'Upload error: HTTP {confirmation.status_code}')
						'''
						If POST failed, need to alert if the recorder starts filling up with .wavs
						The process will exit if the device runs out of space.
						'''
						usage = shutil.disk_usage('/')
						percent_used = usage[1] / usage[0] * 100
						self.my_logger.info('Recording not deleted. System storage used: %.2f%%' % percent_used)
						if percent_used > 95:
							self.my_logger.critical('Microphone crash imminent: Storage used: %.2f%%' % percent_used)
						elif percent_used > 90:
							self.my_logger.warning('System nearly full. Storage used: %.2f%%' % percent_used)

					elif fileid == sha:  # and str(confirmation.status_code) == '200' implied
						os.remove(filename)
						self.my_logger.info("Post to CDN was successful")
						self.my_logger.info("Deleted file: {}".format(filename))

						kafka_hash_q.put({'text': f'{filename}', 'details': {"startTime": str(start_time),
																			 "endTime": str(end_time),
																			 "SHA1": f'{filename}',
																			 "fileSize": str(filesize),
																			 "Room": self.room,
																			 "microphone": self.microphone_number,
																			 "calibration_flag": calibration_flag}})
				except NewConnectionError as e:
					self.my_logger.error(f'Couldn\'t resolve address: {e}')
					tb = traceback.format_exc()
					self.my_logger.error(tb)

					# Read file to the head of the post queue to attempt to POST again
					temp_q = Queue()
					temp_q.put(message)
					while not self.post_queue.empty():
						temp_q.put(self.post_queue.get())
					self.post_queue = temp_q

				except Exception as e:
					self.my_logger.error(f'\npostCDN exception: {e}\n')
					tb = traceback.format_exc()
					self.my_logger.error(tb)

					# Read file to the head of the post queue to attempt to POST again
					temp_q = Queue()
					temp_q.put(message)
					while not self.post_queue.empty():
						temp_q.put(self.post_queue.get())
					self.post_queue = temp_q
				"""


##=============================================================================

if __name__ == "__main__":
	while True:
		try:
			yeti = YetiManager(int(os.environ.get('MIC_NUM', '0')))
			print("[main]  Starting Audio Process")
			yeti.audio_process.start()
			print("[main]  Starting Hash Process")
			yeti.hash_process.start()
			print("[main]  Starting Posting Process")
			yeti.posting_process.start()

			while True:
				time.sleep(0.1)
		except KeyboardInterrupt:
			yeti.kill_all_vlc()
			time.sleep(1)
			sys.exit(0)


##=============================================================================
"""
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

"""