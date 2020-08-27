import os
from time import sleep
from signal import SIGKILL
from dataclasses import dataclass
import subprocess as sproc
import shlex

##=============================================================================

""" 
Dataclass representing specific audio configurations for the VLC commmands that are 
used for duplicate streaming and simultaneous listening of USB microphone audio data.
"""
@dataclass
class VLCAudioSettings:
	## Microphone input MRL for the outgoing live-stream
	tx_mrl: str = "alsa://hw:Microphone"   		#"alsa://hw:2,0"
	## Loopback address MRL for recording the live-stream in parallel
	rx_mrl: str = "rtp://@127.0.0.1:1234"
	## Audio codec for VLC
	codec: str = "mpga"                    		#"s16l" 	#"mp3"
	## Number of audio channels (2 for stereo)
	channels: int = 2                      		#1
	## Audio sampling frequency (in Hz.)
	samplerate: int = 44100                		#48000
	## Audio stream bit rate (256 yields higher quality audio than 128)
	bitrate: int = 128                     		#256


##=============================================================================

class VLCAudioBase():
	""" 
	Base class from which the VLCAudioStreamer and VLCAudioListener subclasses inherit.
	"""
	def __init__(self, audio_settings, verbose_level, executable, protocol):
		assert isinstance(audio_settings, VLCAudioSettings)
		self.cfg = audio_settings 	 ## Must be an `AudioSettings` dataclass instance
		self.v_opt = '-{}'.format('v'*verbose_level) if verbose_level in range(1,4) else '-q'
		self.vlc = executable
		self.proto = protocol


	@property
	def opt_str(self):
		""" Returns the global VLC options shared by both streamers and listeners. """
		return f'{self.v_opt} --no-sout-video --sout-audio --ttl=1 --sout-keep'
	

	@property
	def input_stream(self):
		""" Returns the appropriate audio input_stream MRL to be given to VLC commands. """
		if isinstance(self, VLCAudioStreamer):
			return self.cfg.tx_mrl
		elif isinstance(self, VLCAudioListener):
			return self.cfg.rx_mrl
		return "vlc://quit" 


	@property
	def transcode_str(self):
		""" 

		"""
		## Alternatively, could make this a method within the VLCAudioSettings dataclass 
		return ''.join([
				"transcode{acodec=", self.cfg.codec, 
				",ab=", str(self.cfg.bitrate), 
				",aenc=ffmpeg,channels=", str(self.cfg.channels), 
				",samplerate=", str(self.cfg.samplerate),
				",threads=2}"
				])	


	def update_audio_settings(self, new_settings):
		""" 

		"""
		if isinstance(new_settings, VLCAudioSettings):
			self.cfg = new_settings 	 ## Must be an `AudioSettings` dataclass instance


	@staticmethod
	def get_running_vlc_pid_list(): 
		return [int(pid) for pid in os.popen(f'pidof vlc').read()[:-1].split(' ') if pid]


##=============================================================================
"""
~ Streaming Example ~
[YetiAudioStreamer_0] Stream Command: 
	cvlc -q --no-sout-video --sout-audio --ttl=1 --sout-keep --sout "#transcode{      \
	acodec=mpga,ab=256,aenc=ffmpeg,channels=2,samplerate=44100,threads=2}:duplicate{  \
	dst=rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,name='YetiAudioStream_0'},     \
	dst=rtp{mux=ts,dst=127.0.0.1,port=1234,sdp=sap,name='loopback_0'}}" alsa://hw:Microphone &
"""
class VLCAudioStreamer(VLCAudioBase):
	""" 
	TODO
	"""
	def __init__(self, name, audio_settings, dest_ip_address, dest_port=1234, 
				loopback_addr='127.0.0.1', loopback_port=1234, loopback_name='loopback', 
				verbose_level=0, executable='cvlc', protocol='rtp', logger=None, use_nohup=True):
		## NOTE: Currently no support for any protocol other than RTP; in future, can add support for HTTP streams
		super().__init__(audio_settings, verbose_level, executable, protocol)
		self.name = name 
		self.out_addr = dest_ip_address
		self.out_port = dest_port
		self.dup_out_addr = loopback_addr
		self.dup_out_port = loopback_port
		self.dup_out_name = loopback_name
		self.__state = "STOPPED"
		self.process = None
		self.stream_log = logger
		self.__last_cmd_used_shell = False
		self.nohup = use_nohup
	

	@property
	def state(self):
		return self.__state
	

	@property
	def duplicate_str(self):
		"""
		Formats and returns the VLC 'duplicate' module configuration string for the streaming command;
		this is essential for VLC to stream the audio data to multiple destinations.
		"""
		destination1 = ''.join(["rtp{mux=ts,dst=", self.out_addr, ",port=", str(self.out_port), ",sdp=sap,name='", self.name, "'}"])
		destination2 = ''.join(["rtp{mux=ts,dst=", self.dup_out_addr, ",port=", str(self.dup_out_port), ",sdp=sap,name='", self.dup_out_name, "'}"])
		return ''.join(["duplicate{dst=", destination1, ",dst=", destination2, "}"])
	

	@property
	def sout(self):
		"""
		Formats and returns the 'sout' stream output configuration string for the VLC command; this 
		tells VLC how to transcode the raw audio data ('transcode_str' acquired from VLCAudioBase class)
		and where/how to stream the transcoded audio data to its multiple target addresses.
		"""
		return f"#{self.transcode_str}:{self.duplicate_str}"


	@property
	def stream_cmd(self): 	#, nohup=True): 	#nohup=False):
		"""
		This command will launch a headless VLC instance as a background job to continually stream
		live audio data from the input stream MRL (i.e., USB microphone device identifier) to 
		multiple target addresses (using VLC's 'duplicate' module): one being an RTP address, the
		other being a local loopback address for a VLCAudioListener instance to bind to for capturing
		and processing the live feed's audio data in parallel.
		"""
		self.__stream_cmd = f'{self.vlc} {self.opt_str} --sout "{self.sout}" {self.input_stream} &'
		if self.nohup:
			self.__stream_cmd = 'nohup ' + self.__stream_cmd
		return self.__stream_cmd
	

	@property
	def pid(self):
		""" 
		Returns the streaming VLC background job's PID if the stream's process attribute (an 
		instance of the Popen class from the subprocess Python module) is not None. 
		"""
		# return self.process.pid if self.process else None
		## ^ NOTE: If Popen process was created with shell=True, then process.pid will return PID of parent shell ('sh <defunct>').
		## ^^ If this is the case, then 'process.kill()' or 'process.terminate()' will NOT kill the spawned VLC job.
		## ^^^ See:  https://stackoverflow.com/questions/31039972/python-subprocess-popen-pid-return-the-pid-of-the-parent-script
		if self.process is None:
			return None
		vlc_pid_list = VLCAudioBase.get_running_vlc_pid_list()
		if len(vlc_pid_list) == 1 and self.is_running:
			parent_pid = vlc_pid_list[0]
		else:
			parent_pid = self.process.pid
			if self.__last_cmd_used_shell:
				## If stream launched with 'subprocess.Popen(stream_cmd, shell=True)', 
				## will need to search thru list of active VLC PIDs for successor to parent PID
				if (parent_pid + 1) in vlc_pid_list:
					parent_pid += 1
				elif (parent_pid + 2) in vlc_pid_list:
					parent_pid += 2
		return parent_pid 
		
	

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
		return running 
	

	def display_stream_command(self):
		""" Mostly just for debug purposes. """
		msg = f"[{self.name}]  Stream Command: {self.stream_cmd}"
		if self.stream_log:
			self.stream_log.info(msg)
		else:
			print(f'\n{msg}')


	def update_state(self, new_state):
		if new_state != self.__state:
			self.__state = new_state
			msg = f"[{self.name}]  NEW STATE: {new_state}"
			if self.stream_log:
				self.stream_log.info(msg)
			else:
				print(f'\n{msg}')


	def stream_start(self, use_shell=False):  #use_shell=True):
		"""
		Initiates the audio stream as a background job with a tailored shell command; sets the VLCAudioStreamer's 
		process attribute to the instantiated subprocess.Popen object returned from launching the
		stream command; setting the keyword parameter 'use_shell' to True will spawn a new shell
		process from whence the child VLC stream job is spawned, in which case 'self.process.pid' 
		will return the spawned shell's PID rather than the VLC PID and 'self.process.kill()' will
		be ineffective (requiring the use of a process group by attaching a session id to the spawned
		shell parent process); for more info, see:  
		https://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true
		"""
		if not self.is_running:
			cmd = self.stream_cmd if use_shell else shlex.split(self.stream_cmd)
			self.process = sproc.Popen(cmd, shell=use_shell)
			self.update_state("STREAMING")
		else:
			msg = f"[{self.name}]  Streamer is already streaming audio; call ignored."
			if self.stream_log:
				self.stream_log.info(msg)
			else:
				print(msg)
		self.__last_cmd_used_shell = use_shell


	def stream_stop(self, redundant_kill=False):
		"""
		Kills the VLC audio stream; the optional 'redundant_kill' flag is used only for issuing a 
		redundant kill command to ensure that the background stream is halted in the case subprocess.Popen.kill() command was effective in halting the audio 
		live-stream, then issuing a redundant kill command for the background stream process's PID if still found alive.
		"""
		pid = self.pid 
		if self.process:
			if not self.__last_cmd_used_shell:
				self.process.kill()
			else:
				for found_pid in VLCAudioBase.get_running_vlc_pid_list():  #os.popen(f'pidof vlc').read()[:-1].split(' '):
					try:
						if found_pid == pid or found_pid == (pid + 1) or found_pid == (pid + 2):
							msg = f"[stream_stop]  Now killing VLC child with PID {found_pid}"
							if self.stream_log:
								self.stream_log.info(msg)
							else:
								print(msg)
							os.kill(found_pid, SIGKILL)
					except (ProcessLookupError, TypeError):
						pass	## Ignore errors if the stream process no longer exists or if self.pid is None
			sleep(0.05)
			while self.is_running:
				msg = f"[stream_stop]  Waiting for child process '{self.name}' to terminate..."
				if self.stream_log:
					self.stream_log.warning(msg)
				else:
					print(msg)
				sleep(0.2)
				continue
			self.process = None
		else:
			msg = f"[stream_stop]  Popen process for VLCAudioStreamer '{self.name}' is None!"
			if self.stream_log:
				self.stream_log.warning(msg)
			else:
				print(f'ERROR: {msg}')
		if redundant_kill:
			try:
				if pid != -1:
					msg = f">>> Redundant kill:  Now killing '{self.name}' with PID {pid}"
					if self.stream_log:
						self.stream_log.info(msg)
					else:
						print(f'\n{msg}')
					os.kill(pid, SIGKILL)	## DON'T EVER call os.kill() for pid -1!!
			except (ProcessLookupError, TypeError):
				pass 	## Ignore errors if the stream process no longer exists or if self.pid is None
		self.update_state("STOPPED")
		

## TODO (optional): Additional methods for controlling stream, reading CPU usage, etc.

##=============================================================================

### cvlc -q --no-sout-video --sout-audio --ttl=1 --sout-keep \
### --sout "#transcode{acodec=mpga,ab=256,aenc=ffmpeg,channels=2,samplerate=44100,threads=2}:std{access=file,mux=wav,dst=output.wav}" \
### rtp://@127.0.0.1:1234 vlc://quit &

"""
~ Listening Example ~
[YetiAudioListener_0] Listen Command: 
	cvlc -q --no-sout-video --sout-audio --ttl=1 --sout-keep --sout "#transcode{  \
	acodec=mpga,ab=256,aenc=ffmpeg,channels=2,samplerate=44100,threads=2}:std{    \
	access=file,mux=wav,dst=output0.wav}" rtp://@127.0.0.1:1234 vlc://quit &
"""
class VLCAudioListener(VLCAudioBase):
	""" 
	TODO
	"""
	def __init__(self, name, audio_settings, capture_format='wav', capture_duration=30, 
				verbose_level=0, executable='cvlc', protocol='rtp', logger=None, use_nohup=True):
		super().__init__(audio_settings, verbose_level, executable, protocol)
		self.name = name 
		self.clip_format = capture_format.lower()
		self.recording_duration = capture_duration
		self.__state = "STOPPED"
		self.process = None
		self.listen_log = logger
		self.__last_cmd_used_shell = False
		self.nohup = use_nohup


	@property
	def state(self):
		return self.__state


	@property
	def clip_filename(self):
		""" 
			
		"""
		clip_num = 0
		while f"output{clip_num}.{self.clip_format}" in (os.listdir()):
			clip_num += 1
		self.__current_clip_name = f"output{clip_num}.{self.clip_format}"
		return os.path.join(os.getcwd(), self.__current_clip_name)
	

	@property
	def save_clip_str(self):
		""" 

		"""
		return ''.join(["std{access=file,mux=", self.clip_format, ",dst=", self.clip_filename, "}"])
	

	@property
	def sout(self):
		""" 

		"""
		return f"#{self.transcode_str}:{self.save_clip_str}"


	@property
	def listen_cmd(self): 	#, nohup=True): 	#nohup=False):
		""" 

		"""
		self.__listen_cmd = f'{self.vlc} {self.opt_str} --sout "{self.sout}" {self.input_stream} vlc://quit &'
		if self.nohup:
			self.__listen_cmd = 'nohup ' + self.__listen_cmd
		return self.__listen_cmd


	@property
	def pid(self):
		# return self.process.pid if self.process else None
		## ^ NOTE: If Popen process was created with shell=True, then process.pid will return PID of parent shell ('sh <defunct>').
		## ^^ If this is the case, then 'process.kill()' or 'process.terminate()' will NOT kill the spawned VLC job.
		## ^^^ See:  https://stackoverflow.com/questions/31039972/python-subprocess-popen-pid-return-the-pid-of-the-parent-script
		if self.process is None:
			return None
		vlc_pid_list = VLCAudioBase.get_running_vlc_pid_list()
		if len(vlc_pid_list) == 1 and self.is_running:
			parent_pid = vlc_pid_list[0]
		else:
			parent_pid = self.process.pid
			if self.__last_cmd_used_shell:
				## If listener launched with 'subprocess.Popen(listen_cmd, shell=True)', 
				## will need to search thru list of active VLC PIDs for successor to parent PID
				if (parent_pid + 1) in vlc_pid_list:
					parent_pid += 1
				elif (parent_pid + 2) in vlc_pid_list:
					parent_pid += 2
		return parent_pid 


	@property
	def is_running(self):
		if self.process is None:
			if self.__state != "STOPPED":
				self.update_state("STOPPED")
			return False
		running = self.process.poll() is None 	## Popen.poll() returns the exit code of child process if it has terminated, else None
		if running and self.__state != "RECORDING":
			self.update_state("RECORDING")
		elif not running and self.__state != "STOPPED":
			self.update_state("STOPPED")
		return running 


	def display_listen_command(self):
		msg = f"[{self.name}]  Listen Command: {self.listen_cmd}"
		if self.listen_log:
			self.listen_log.info(msg)
		else:
			print(f'\n{msg}')


	def set_recording_duration(self, duration):
		try:
			self.recording_duration = float(duration)
		except ValueError:
			pass


	def update_state(self, new_state):
		if new_state != self.__state:
			self.__state = new_state
			msg = f"[{self.name}]  NEW STATE: {new_state}"
			if self.listen_log:
				self.listen_log.info(msg)
			else:
				print(f'\n{msg}')


	def listen_start(self, use_shell=False): 	#use_shell=True):
		"""

		"""
		if not self.is_running:
			cmd = self.listen_cmd if use_shell else shlex.split(self.listen_cmd)
			msg = f"[{self.name}]  Listener recording new clip:  '{self.__current_clip_name}'"
			if self.listen_log:
				self.listen_log.info(msg)
			else:
				print(msg)
			self.process = sproc.Popen(cmd, shell=use_shell)
			self.update_state("RECORDING")
		else:
			msg = f"[{self.name}]  Listener is already recording loopback audio; call ignored."
			if self.listen_log:
				self.listen_log.info(msg)
			else:
				print(msg)
		self.__last_cmd_used_shell = use_shell


	def listen_stop(self, redundant_kill=False):
		""" 

		"""
		pid = self.pid
		if self.process:
			if not self.__last_cmd_used_shell:
				self.process.kill()
			else:
				for found_pid in VLCAudioBase.get_running_vlc_pid_list():
					try:
						if found_pid == pid or found_pid == (pid + 1) or found_pid == (pid + 2):
							msg = f"[listen_stop]  Now killing VLC child with PID {found_pid}"
							if self.listen_log:
								self.listen_log.info(msg)
							else:
								print(msg)
							os.kill(found_pid, SIGKILL)
					except (ProcessLookupError, TypeError):
						pass	## Ignore errors if the stream process no longer exists or if self.pid is None
			sleep(0.05)
			while self.is_running:
				msg = f"[listen_stop]  Waiting for child process '{self.name}' to terminate..."
				if self.listen_log:
					self.listen_log.warning(msg)
				else:
					print(msg)
				sleep(0.2)
				continue
			msg = f"[{self.name}]  Listener successfully captured audio clip:  '{self.__current_clip_name}'"
			if self.listen_log:
				self.listen_log.info(msg)
			else:
				print(msg)
			self.process = None
		else:
			msg = f"[listen_stop]  Popen process for VLCAudioListener '{self.name}' is None!"
			if self.listen_log:
				self.listen_log.warning(msg)
			else:
				print(f'ERROR: {msg}')
		if redundant_kill:
			try:
				if pid != -1:
					msg = f">>> Redundant kill:  Now killing '{self.name}' with PID {pid}"
					if self.listen_log:
						self.listen_log.info(msg)
					else:
						print(f'\n{msg}')
					os.kill(pid, SIGKILL)	## DON'T call os.kill() for pid -1!!
			except (ProcessLookupError, TypeError):
				pass	## Ignore errors if the stream process no longer exists or if self.pid is None
		self.update_state("STOPPED")


	def get_recent_clip(self):
		""" 
		
		"""
		## FIXME: Is this really the best way to go about this? This may require the listener's own collection of unprocessed files,
		##        in case of a pipeline backup (i.e., if CDN or Kafka communications issues occur)
		## ^ Honestly, there should only ever be enough overlap between the recording audio process && the audio hashing process to miss a single file... so this may be sufficient
		current_clip_name = self.__current_clip_name
		self.__current_clip_name = None
		return current_clip_name


##=============================================================================
