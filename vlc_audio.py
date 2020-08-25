import os
from time import sleep
from signal import SIGKILL
from dataclasses import dataclass
import subprocess as sproc
import shlex

##=============================================================================

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
	def __init__(self, audio_settings, verbose_level, executable, protocol):
		assert isinstance(audio_settings, VLCAudioSettings)
		self.cfg = audio_settings 	 ## Must be an `AudioSettings` dataclass instance
		self.v_opt = '-{}'.format('v'*verbose_level) if verbose_level in range(1,4) else '-q'
		self.vlc = executable
		self.proto = protocol


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


	def update_audio_settings(self, new_settings):
		if isinstance(new_settings, VLCAudioSettings):
			self.cfg = new_settings 	 ## Must be an `AudioSettings` dataclass instance


##=============================================================================

class VLCAudioStreamer(VLCAudioBase):
	def __init__(self, name, audio_settings, dest_ip_address, dest_port=1234, 
				loopback_addr='127.0.0.1', loopback_port=1234, loopback_name='loopback', 
				verbose_level=0, executable='cvlc', protocol='rtp', logger=None):
		## NOTE: Currently no support for any protocol other than RTP; in future, can add support for HTTP streams
		self.name = name 
		super().__init__(audio_settings, verbose_level, executable, protocol)
		self.out_addr = dest_ip_address
		self.out_port = dest_port
		self.dup_out_addr = loopback_addr
		self.dup_out_port = loopback_port
		self.dup_out_name = loopback_name
		self.__state = "STOPPED"
		self.process = None
		self.stream_log = logger
	

	@property
	def state(self):
		return self.__state
	

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
		return running 
	

	def display_stream_command(self):
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


	def stream_start(self, use_shlex=False, use_shell=True):
		if not self.is_running:
			cmd = self.stream_cmd if not use_shlex else shlex.split(self.stream_cmd)
			self.process = sproc.Popen(cmd, shell=use_shell)
			self.update_state("STREAMING")


	def stream_stop(self, redundant_kill=False):
		if self.process:
			self.process.kill()
			if redundant_kill:
				try:
					if self.pid != -1:
						os.kill(self.pid, SIGKILL)	## DON'T call os.kill() for pid -1!!
				except (ProcessLookupError, TypeError):
					pass
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
				self.stream_log.error(msg)
			else:
				print(f'ERROR: {msg}')
		self.update_state("STOPPED")
		

## TODO (optional): Additional methods for controlling stream, reading CPU usage, etc.

##=============================================================================

### cvlc -q --no-sout-video --sout-audio --ttl=1 --sout-keep \
### --sout "#transcode{acodec=mpga,ab=256,aenc=ffmpeg,channels=2,samplerate=44100,threads=2}:std{access=file,mux=wav,dst=output.wav}" \
### rtp://@127.0.0.1:1234 vlc://quit &

class VLCAudioListener(VLCAudioBase):
	def __init__(self, name, audio_settings, capture_format='wav', capture_duration=30, 
						verbose_level=0, executable='cvlc', protocol='rtp', logger=None):
		super().__init__(audio_settings, verbose_level, executable, protocol)
		self.name = name 
		self.clip_format = capture_format.lower()
		self.recording_duration = capture_duration
		self.__state = "STOPPED"
		self.process = None
		self.listen_log = logger


	@property
	def clip_filename(self):
		clip_num = 0
		while f"output{clip_num}.{self.clip_format}" in (os.listdir()):
			clip_num += 1
		self.__current_clip_name = f"output{clip_num}.{self.clip_format}"
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
		msg = f"[{self.name}]  Listen Command: {self.listen_cmd}"
		if self.listen_log:
			self.listen_log.info(msg)
		else:
			print(f'\n{msg}')


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
		if running and self.__state != "RECORDING":
			self.update_state("RECORDING")
		elif not running and self.__state != "STOPPED":
			self.update_state("STOPPED")
		return running 


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


	def listen_start(self, use_shlex=False, use_shell=True):
		if not self.is_running:
			cmd = self.listen_cmd if not use_shlex else shlex.split(self.listen_cmd)
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


	def listen_stop(self, redundant_kill=False):
		if self.process:
			self.process.kill()
			if redundant_kill:
				try:
					if self.pid != -1:
						os.kill(self.pid, SIGKILL)	## DON'T call os.kill() for pid -1!!
				except (ProcessLookupError, TypeError):
					pass
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
				self.listen_log.error(msg)
			else:
				print(f'ERROR: {msg}')
		self.update_state("STOPPED")


	def get_recent_clip(self):
		## FIXME: Is this really the best way to go about this? This may require the listener's own collection of unprocessed files,
		##        in case of a pipeline backup (i.e., if CDN or Kafka communications issues occur)
		## ^ Honestly, there should only ever be enough overlap between the recording audio process && the audio hashing process to miss a single file... so this may be sufficient
		current_clip_name = self.__current_clip_name
		self.__current_clip_name = None
		return current_clip_name


##=============================================================================
