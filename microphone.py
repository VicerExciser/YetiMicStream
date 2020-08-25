import os
import sys
import time
import hashlib
import datetime as dt
import requests
import traceback
import shutil
from urllib3.exceptions import NewConnectionError
from multiprocessing import Queue, Process, Lock, Value 
from vlc_audio import VLCAudioSettings, VLCAudioStreamer, VLCAudioListener

"""
To receive the audio stream from another machine, simply run the command:
	
			$  vlc rtp://@<stream IP address>:<stream port>
	e.g.,
			$  vlc -vv rtp://@239.255.12.42:1234
"""

SEGREGATED_TEST_MODE = True  ## Set to False for integration testing w/ Alcazar CnC API
DRY_RUN = True  ## Will skip any network-dependent tasks if set to True (i.e., posting to the CDN or Kafka)

if not SEGREGATED_TEST_MODE:
	from alcazar_common.cnc.cnc_base import SensorBase
	from alcazar_common.models import telem_message as model
	from alcazar_common.logger import get_logger
else:
	## Using shallow classes as mock replacements for Alcazar CnC modules
	import typing 

	class SensorBase():
		def __init__(self, component_site='component_site', component_type='component_type', component_id=None,
						 component_name='component_name', topics='CNC.CONTROL.*',
						 component_friendly_name="component_friendly_name"):
			self.component_site = component_site
			self.component_type = component_type
			self.component_id = component_id
			self.component_name = component_name
			self.topics = topics
			self.component_friendly_name = component_friendly_name
			self.__state = ''
			self.logger = get_logger('cnc_base')
			self.ready = False

		def set_ready(self, ready):
			self.ready = ready

		def start(self):
			self.set_ready(True)
			self.update_state("Running")

		def add_message_callback(self, value, message):
			pass

		def update_state(self, new_state):
			self.__state = new_state
			print(f"[update_state] New state:  {new_state}")

		def shutdown(self):
			pass

		def send_alert(self, subtype: str, severity: int, confidence: int,
				   title: str, text: str, details: dict = None,
				   message_refs: typing.List[str] = None,
				   component_name: typing.Optional[str] = None,
				   component_site: typing.Optional[str] = None):
			print(f"[send_alert] Severity: {severity}; Title: {title}; Text: {text}")

		@staticmethod
		def _get_timestamp():
			""" Return the timestamp formatted correctly as per the ICD. """
			return '{}Z'.format(dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])

	# -------------------------------------------------------------------------------------

	class get_logger():
		def __init__(self, name):
			self.name = f'{name}_logger'

		def log_to_console(self, msg):
			print(msg)

		def warning(self, msg):
			self.log_to_console(f'[WARNING]  {msg}')

		def error(self, msg):
			self.log_to_console(f'[ERROR]  {msg}')

		def info(self, msg):
			self.log_to_console(f'[INFO]  {msg}')

		def critical(self, msg):
			self.log_to_console(f'[INFO]  {msg}')


##=============================================================================
## TODO: Extract other globals from the MicrophoneSensor class && add here

cdn_url = os.getenv('CDNURL', 'pipeline-cdn.telemetry.svc.kube.local')
cdn_port = os.getenv('CDNPORT', '5000')

##=============================================================================

class MicrophoneSensor(SensorBase):
	"""
	Subclass for a Yeti Microphone.
	Inherits from and implements the CNCBase abstract class.
	"""
	RECALIB_ON_REBOOT = True

	def __init__(self, component_site, mic_number):
		super().__init__(component_site=component_site,
						 component_type='SENSOR' if SEGREGATED_TEST_MODE else model.ComponentTypes.Sensor.value,
						 component_id=None,
						 component_name='microphone',
						 topics='CNC.CONTROL.*',
						 component_friendly_name=f"Blue Yeti Microphone - {component_site}")
		self.room = component_site
		self.microphone_number = mic_number

		self.stream_name = f"YetiAudioStream_{self.microphone_number}"
		self.listener_name = f"YetiAudioListener_{self.microphone_number}"
		self.loopback_name = f"loopback_{self.microphone_number}"
		self.__device_name = None
		self.vlc_exe = "cvlc" if sys.platform != "darwin" else "/Applications/VLC.app/Contents/MacOS/VLC -I dummy"

		## Calibration flag
		self.do_calibration_flag = Value('i', 0)
		self.calibration_lock = Lock()
		self.calibration_duration = 31

		self.my_logger = get_logger('microphone')
		self.my_logger.info('My id: {}'.format(self.component_id))
		self.update_state("Initializing")

		if not SEGREGATED_TEST_MODE:
			self.add_message_callback(model.ControlMessageSubtypes.Microphone.value, self.do_parse_control_message)
		
		## The duration multiplier accounts for sample rate skew between the Blue Yeti and real time (Time is in seconds)
		self.sampling_multiplier = 1.036
		self.file_duration = self.truncate(float(os.getenv("RECORDING_DURATION", "30")) * self.sampling_multiplier, 3)
		self.duration_update = True
		self.duration_lock = Lock()
		self.start_time = ''
		self.end_time = ''
		self.filename = None

		## Multiprocessing queues
		self.post_queue = Queue()
		self.hash_queue = Queue()
		self.kafka_queue = Queue()  ## Needed since producers cannot be shared across processes
		
		## Audio settings for streaming && recording
		## TODO: Read these configuration values in from a file ( or set them as environment variables )
		self.stream_rtp_addr = os.getenv("STREAM_RTP_ADDR", "239.255.12.42")
		self.stream_rtp_port = int(os.getenv("STREAM_RTP_PORT", "1234"))
		self.loopback_addr = os.getenv("STREAM_LOOP_ADDR", "127.0.0.1")     ## <-- Address to listen on for stream audio processing/saving
		self.loopback_port = int(os.getenv("STREAM_LOOP_PORT", "1234"))
		self.recording_format = os.getenv("RECORDING_FORMAT", "WAV").lower()
		self.verbose_level = int(os.getenv("STREAM_VERBOSE_LEVEL", "0"))    ## 0 = -q, 1 = -v, 2 = -vv, 3 = -vvv
		self.streaming_protocol = os.getenv("STREAM_PROTOCOL", "RTP").lower()
		self.CODEC = os.getenv("STREAM_ACODEC", "MPGA").lower()  #"s16l"
		self.CHANNELS = int(os.getenv("STREAM_CHANNELS", "2"))  #1
		self.SAMPLERATE = int(os.getenv("STREAM_SAMPLERATE", "44100"))  #48000
		self.BITRATE = int(os.getenv("STREAM_BITRATE", "256"))  #128


		self.settings = VLCAudioSettings(self.stream_mrl, self.loop_mrl, self.CODEC, self.CHANNELS, self.SAMPLERATE, self.BITRATE)

		self.streamer = VLCAudioStreamer(self.stream_name, self.settings, self.stream_rtp_addr, dest_port=self.stream_rtp_port, 
				loopback_addr=self.loopback_addr, loopback_port=self.loopback_port, loopback_name=self.loopback_name,
				verbose_level=self.verbose_level, executable=self.vlc_exe, protocol=self.streaming_protocol, logger=self.my_logger)
		## For DEBUG:
		# self.streamer.display_stream_command()

		self.listener = VLCAudioListener(self.listener_name, self.settings, 
				capture_format=self.recording_format, capture_duration=self.file_duration, 
				verbose_level=self.verbose_level, executable=self.vlc_exe, protocol=self.streaming_protocol, logger=self.my_logger)
		## For DEBUG:
		# self.listener.display_listen_command()


		## Processes
		self.my_logger.info(f'[{self.__class__.__name__}]  Initializing Audio Process')
		self.audio_process = Process(target=self.get_audio, args=(self.hash_queue, self.duration_lock, 
													self.do_calibration_flag, self.calibration_lock))
	   
		self.my_logger.info(f'[{self.__class__.__name__}]  Initializing Hash Process')
		self.hash_process = Process(target=self.hash_audio_for_post, args=(self.hash_queue, self.post_queue))  #, self.do_calibration_flag))

		self.my_logger.info(f'[{self.__class__.__name__}]  Initializing Posting Process')
		self.posting_process = Process(target=self.post_cdn, args=(self.post_queue, self.kafka_queue))

		## Set all process daemons
		self.my_logger.info(f'[{self.__class__.__name__}]  Setting all processes to daemon=True')
		self.audio_process.daemon = True
		self.hash_process.daemon = True
		self.posting_process.daemon = True

		## Clean up ephemeral recordings from previous containers
		try:
			self.wav_check(self.post_queue)
		except Exception as e:
			self.my_logger.error(e)


	@property
	def device_name(self):
		if self.__device_name is None:
			try:
				self.__device_name = [card[card.find('[')+1:card.find(']')].strip() for card in os.popen('cat /proc/asound/cards').read().split('\n') if all(x in card for x in ['Yeti', '['])][0]
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

	@property
	def stream_target_url(self):
		return f"rtp://@{self.stream_rtp_addr}:{self.stream_rtp_port}"
	
	
	def get_audio(self, hash_q, duration_lock, calibration_flag, calibration_lock):
		self.my_logger.info('Audio Process Successfully Started')
		self.my_logger.info(f'Initializing VLC live-stream of audio data to target address ({self.stream_target_url})')
		self.streamer.stream_start()
		self.update_state("Streaming")
		time.sleep(3)   ## Slight delay to allow VLC stream to init && stabilize
		calibrating = False
		self.my_logger.info(f'Initializing VLC loopback listener for recording audio data ({self.loop_mrl})')
		self.my_logger.info('Recording...')
		self.update_state("Recording")
		while True:
			if self.duration_update:
				self.update_state("Changing recording duration")
				self.my_logger.info('get_audio: Acquiring recording duration lock...')
				duration_lock.acquire()   ## Blocking
				self.my_logger.info('get_audio: Recording duration lock acquired. Opening audio stream.')
				try:
					self.listener.set_recording_duration(self.file_duration)
				finally:
					self.duration_update = False
					duration_lock.release()
			else:
				if calibration_flag.value:
					self.update_state("Calibrating")
					calibrating = True
					self.my_logger.info("Beginning Calibration")
			try:
				record_seconds = self.listener.recording_duration if not calibrating else self.calibration_duration
				clip_start_time = SensorBase._get_timestamp()
				capture_ts = time.time()
				self.listener.listen_start()
				while (time.time() - capture_ts) <= record_seconds:
					time.sleep(0.1)
				self.listener.listen_stop()
				clip_end_time = SensorBase._get_timestamp()
				temp_recording_name = self.listener.get_recent_clip()
				if os.path.isfile(temp_recording_name):
					hash_q.put((temp_recording_name, clip_start_time, clip_end_time, calibrating))
				else:
					self.my_logger.error(f"[get_audio] No saved audio file named '{temp_recording_name}' was found!")
					time.sleep(1)
				if calibrating:
					calibrating = False
					self.my_logger.info("Ending Calibration")
					with calibration_lock:
						calibration_flag.value = 0
					self.update_state("Recording")
			except Exception as exc_1:
					self.my_logger.error("Error in get_audio: {}".format(exc_1))
			# finally:
			#   if calibrating:
			#       self.listener.set_recording_duration(self.file_duration)

				
	def kill_all_vlc(self):
		self.my_logger.info(f"\n[{self.__class__.__name__}]  Aborting: Terminating all VLC activities.")
		self.listener.listen_stop()
		self.streamer.stream_stop()
	

	def hash_audio_for_post(self, hash_q, post_q):
		self.my_logger.info('Hash Process Successfully Started')
		while True:
			while not hash_q.empty():
				try:
					unprocessed_data = hash_q.get()
					temp_filename = unprocessed_data[0]
					self.my_logger.info(f'Hash process received a new file ({temp_filename})')
					## Need to do this to prevent self.start_time and end_time from being overwritten
					self.start_time = unprocessed_data[1]
					self.end_time = unprocessed_data[2]
					calibration_flag = unprocessed_data[3]
					## Rename recording && add it to the CDN post queue
					self.hash_rename(post_q, audio_name=temp_filename, calibration_flag=calibration_flag)
				except Exception as e:
					self.my_logger.error("Exception in hash_audio_for_post: {}".format(e))

					
	def hash_rename(self, post_q, audio_name="output0.wav", calibration_flag=False):
		try:
			with open(audio_name, 'rb') as f:
				audio_data = f.read()
				h = hashlib.new('sha1', audio_data)
				self.filename = h.hexdigest() + f".{self.recording_format}"
			## Rename the audio file to its SHA
			os.rename(audio_name, self.filename)
			self.my_logger.info(f"Audio file '{audio_name}' has been renamed to '{self.filename}'")
			self.add_to_post_q(post_q, self.filename, calibration_flag=calibration_flag)
		except Exception as e:
			self.my_logger.error("Exception in hash_rename: {}".format(e))
				

	def add_to_post_q(self, post_q, filename, calibration_flag=False):
		filesize = os.path.getsize(filename)
		## Put all the data into the posting queue as a dictionary for easy unpacking
		post_q.put({
			"filename": filename,
			"file_size": filesize,
			"sha": filename.split('.')[0],
			"start_t": self.start_time,
			"end_t": self.end_time,
			"calibration": calibration_flag })
		## Clear the start and end timestamps
		self.start_time = ''
		self.end_time = ''


	def post_cdn(self, post_q, kafka_q):
		"""
		Checks the post_queue, and parses the dictionary put there by the hash_rename/add_to_post_q functions;
		posts the recorded .wav file to the CDN then runs several checks to ensure it was properly placed there.
		:return:
		"""
		self.my_logger.info('Posting Process Successfully Started')
		while True:
			while not post_q.empty():
				## Get the associated info from the message
				message = post_q.get()
				filename = message["filename"]
				self.my_logger.info(f'Posting process received a new file ({filename})')
				calibration_flag = message["calibration"]
				filesize = message["file_size"]
				sha = message["sha"]
				start_time = message["start_t"]
				end_time = message["end_t"]

				if DRY_RUN:
					try:
						self.my_logger.info(f"[MOCK-post_to_cdn]  Posting data to CDN: {message}")
						time.sleep(1)
						self.my_logger.info(f"[MOCK-post_to_cdn]  Post to CDN was successful --> removing file '{filename}'")
						os.remove(filename)
					except:
						pass
					continue
				
				try:
					self.my_logger.info('Posting to the CDN ...')
					files = {'files': open(filename, 'rb')}
					response = requests.post(f'http://{cdn_url}:{cdn_port}/upload', files=files)
					fileid = response.text.split()[-1]

					## Ensure SHA posted matches the current file's SHA
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
					elif fileid == sha:   ## And str(confirmation.status_code) == '200' implied
						os.remove(filename)
						self.my_logger.info("Post to CDN was successful")
						self.my_logger.info("Deleted file: {}".format(filename))

						kafka_q.put({'text': f'{filename}', 'details': {"startTime": str(start_time),
																		"endTime": str(end_time),
																		"SHA1": f'{filename}',
																		"fileSize": str(filesize),
																		"Room": self.room,
																		"microphone": self.microphone_number,
																		"calibration_flag": calibration_flag}})
				
				except (NewConnectionError, Exception) as e:
					self.my_logger.error(f'\npostCDN exception: {e}\n')
					tb = traceback.format_exc()
					self.my_logger.error(tb)

					## Read file to the head of the post queue to attempt to POST again
					temp_q = Queue()
					temp_q.put(message)
					while not self.post_queue.empty():
						temp_q.put(self.post_queue.get())
					self.post_queue = temp_q
				

	def wav_check(self, post_queue):
		""" This function runs during __init__ to flush out and post any residual .wav files. """
		notify = False   ## Send a single message instead of spamming for each .wav
		for f in os.listdir():
			if ".wav" in f and "calibration" not in f:
				notify = True
				self.end_time = dt.datetime.fromtimestamp(os.stat(f).st_mtime).strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
				## Low priority: TODO: rebuild start time using end time - sample rate * number of frames
				if "output" in f:   ## Last recording not renamed to SHA1
					f.close()
					self.hash_rename(post_queue, audio_name=f)
				else:               ## Files already renamed to SHA1
					self.add_to_post_q(post_queue, f)
		if notify:
			self.my_logger.warning("Residual .wav(s) found! Files sent to the CDN posting queue...")


	@staticmethod
	def truncate(f, n):
		""" Truncates/pads a float f to n decimal places without rounding """
		s = '{}'.format(f)
		if 'e' in s or 'E' in s:
			return '{0:.{1}f}'.format(f, n)
		i, p, d = s.partition('.')
		return float('.'.join([i, (d + '0' * n)[:n]]))


	def do_reboot(self, validated_message):
		self.do_activate(validated_message)

	def do_refresh(self, validated_message):
		self.do_reboot(validated_message)

	def do_activate(self, validated_message):
		self.set_ready(True)  # calls cnc_base's send_heartbeat()

	def do_deactivate(self, validated_message):
		self.set_ready(False)
		self.update_state("Deactivated")

	def shutdown(self):
		self.kill_all_vlc()
		self.posting_process.join(timeout=5)
		self.hash_process.join(timeout=5)
		self.audio_process.join(timeout=5)
		super(MicrophoneSensor, self).shutdown()

	def do_parse_control_message(self, validated_message):
		self.my_logger.info(f'Received: {validated_message}')
		try:
			command_details = validated_message['messageBody']['commandDetail']
			command_message_id = validated_message['messageId']
			command = command_details['command']
			self.send_acknowledgement(command, command_message_id)
			if command != 'calibrate':
				command_value = self.truncate(float(command_details['value']), 3)
				if command == 'duration':
					if command_value > 0:
						if command_value != self.file_duration:
							self.update_file_duration(command_value)
						else:
							self.my_logger.warning('Recording duration already set to the requested value.')
					else:
						self.my_logger.error('Must enter a positive value for the recording length.')
				## Debug command to aid in matching the commanded recording length to the actual length of audio recorded
				elif command == 'multiplier':
					if self.sampling_multiplier != command_value:
						self.sampling_multiplier = command_value
						self.update_file_duration(self.file_duration)
					else:
						self.my_logger.warning('Multiplier already set to the requested value.')
			else:   ## Calibrate
				self.my_logger.info('Received Calibrate Command. Setting do_calibration_flag')
				with self.calibration_lock:
					self.do_calibration_flag.value = 1
		except Exception as e:
			self.my_logger.warning(e)


	def send_acknowledgement(self, command, message_reference):
		if SEGREGATED_TEST_MODE:
			self.send_alert("ACK", 6, 2, 'Command Acknowledgement', f"Acknowledgement of: {command}", None, [message_reference])
		else:
			self.send_alert(model.AlertMessageSubtypes.Acknowledgement.value, 6, 2, 'Command Acknowledgement', f"Acknowledgement of: {command}", None, [message_reference])
		self.my_logger.info('Acknowledgement Sent')


	def update_file_duration(self, next_duration):
		"""
		Safely update self.file_duration.

		This function should only ever be called when the recording length or multiplier have changed.
		Input validation is performed in the do_parse_control_message() function.
		"""
		self.my_logger.info('update_file_duration: Acquiring recording duration lock...')
		self.duration_lock.acquire()   ## Blocking
		self.my_logger.info('update_file_duration: Recording duration lock acquired.\nUpdating recording duration...')
		try:
			self.file_duration = self.truncate(next_duration * self.sampling_multiplier, 3)
		except Exception as e:
			self.my_logger.error(f'update_file_duration: Duration failed to update:\n{e}')
		finally:
			self.duration_lock.release()
			self.duration_update = True   ## Tells the get_audio Process to grab the new duration
			self.my_logger.info('New recording duration set.')


##=============================================================================

if __name__ == "__main__":
	while True:
		sensor = None 
		try:
			room = os.environ.get('ROOM', 'UnknownRoom')
			mic_number = os.environ.get('MIC_NUM', '0')
			sensor = MicrophoneSensor(room, int(mic_number))
			sensor.start()
			sensor.my_logger.info(" Starting Audio Process ...")
			sensor.audio_process.start()
			sensor.my_logger.info(" Starting Hash Process ...")
			sensor.hash_process.start()
			sensor.my_logger.info(" Starting Posting Process ...")
			sensor.posting_process.start()

			while True:
				if not sensor.kafka_queue.empty():
					data = sensor.kafka_hash_q.get()
					if data['details']['calibration_flag']:
						sensor.update_state("Recording_")
						if SEGREGATED_TEST_MODE:
							sensor.send_alert("Status", 5, 2, 'Microphone Calibration CDN Hash', data['text'], data['details'])
						else:
							sensor.send_alert(model.AlertMessageSubtypes.Status.value, 5, 2, 'Microphone Calibration CDN Hash', data['text'], data['details'])
						sensor.my_logger.info(f"Calibration Alert sent to Kafka: {data['text']}")
					else:
						if SEGREGATED_TEST_MODE:
							sensor.send_alert("Status", 5, 2, 'Microphone CDN Hash', data['text'], data['details'])
						else:
							sensor.send_alert(model.AlertMessageSubtypes.Status.value, 5, 2, 'Microphone CDN Hash', data['text'], data['details'])
						sensor.my_logger.info(f"Hash Alert sent to Kafka: {data['text']}")

				# time.sleep(0.1)
			## Do sensor.shutdown()?
			## Break out of the container while loop / raise an exception to restart container?

		except KeyboardInterrupt:
			if sensor is not None:
				sensor.do_deactivate('^C received, deactivating...')
				sensor.shutdown()
			else:
				print('^C received, aborting...')
			time.sleep(1)
			sys.exit(0)
		except Exception as exc:
			if sensor is not None:
				sensor.my_logger.error(exc)
			else:
				print(exc)

##=============================================================================
