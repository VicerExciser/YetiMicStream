import datetime as dt
import time
import wave
import pyaudio  # <-- Note: Requires `sudo apt-get install -y python3-pyaudio` for __portaudio shared object files
import sys
import requests
import traceback
import hashlib
import os
import shutil
import numpy as np
# from threading import Thread
from multiprocessing import Process, Queue, Lock, Value
from urllib3.exceptions import NewConnectionError


SKIP_POST_CDN = True

cdn_url = os.getenv('CDNURL', 'localhost')  #'pipeline-cdn.telemetry.svc.kube.local')
cdn_port = os.getenv('CDNPORT', '5000')

# -------------------------------------------------------------------------------------

class MockSensorBase():
	@staticmethod
	def _get_timestamp():
		"""
		Return the timestamp formatted correctly as per the ICD.
		"""
		return '{}Z'.format(
			dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
		)

# -------------------------------------------------------------------------------------

class MockLogger():
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

# -------------------------------------------------------------------------------------

class Microphone():
	def __init__(self, mic_number):
		self.microphone_number = mic_number
		
		# calibration flag
		self.do_calibration_flag = Value('i', 0)
		self.calibration_lock = Lock()

		self.calibration_duration = 31

		self.my_logger = MockLogger('microphone')
		self.my_logger.info('Microphone number: {}'.format(self.microphone_number))
		self.update_state("Initializing")

		# The duration multiplier accounts for sample rate skew between the Blue Yeti and real time.
		# Time is in seconds.
		self.sampling_multiplier = 1.036
		self.file_duration = self.truncate(float(os.getenv('RECORDING_DURATION', '30')) * self.sampling_multiplier, 3)
		self.duration_update = True
		self.duration_lock = Lock()
		self.start_time = ''
		self.end_time = ''
		self.filename = None

		# queues
		self.post_queue = Queue()
		self.frame_q = Queue()
		self.kafka_hash_q = Queue()  # Needed since producers cannot be shared across processes

		# Audio Globals
		self.CHANNELS = 1
		self.FORMAT = pyaudio.paInt16
		self.RATE = 44100
		self.mic_index = None

		while self.mic_index == None:
			self.p = pyaudio.PyAudio()
			# Get hardware index from microphone name
			self.my_logger.info('Getting sound device info...')
			info = self.p.get_host_api_info_by_index(0)

			numdevices = info.get('deviceCount')
			for i in range(0, numdevices):
				if (self.p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
					try:
						self.my_logger.info(self.p.get_device_info_by_index(i))  # uncomment to see all devices
						# checks each device index to see if it is labeled as Blue Yeti
						if 'Yeti' in self.p.get_device_info_by_index(i)['name']:
							self.mic_index = self.p.get_device_info_by_index(i)['index']
							self.my_logger.info(f'Yeti Index: {self.mic_index}')
							break
					except Exception as e:
						self.my_logger.error(f"exception at device index {i}, {e}")

			if self.mic_index == None:  # Do not compare with 'is not' because the index can be '0'
				self.my_logger.warning("'Blue Yeti' not found, reinstantiating PyAudio...")
				self.p.terminate()
				time.sleep(1)

		self.stream = None
		self.CHUNK = 8 * 1024
		self.NCHUNKS = None

		# processes
		self.my_logger.info('Initializing Audio Process')
		self.audio_process = Process(target=self.get_audio, args=(self.frame_q, self.p, self.duration_lock,
																  self.do_calibration_flag, self.calibration_lock))
		self.my_logger.info('Initializing Hash Process')
		self.hash_process = Process(target=self.frames_to_hash, args=(self.frame_q, self.post_queue))
		self.my_logger.info('Initializing Posting Process')
		self.posting_process = Process(target=self.post_cdn, args=(self.post_queue, self.kafka_hash_q))
		self.my_logger.info('Initializing Streaming Process')
		self.streaming_process = Process(target=self.stream_audio, args=(self.post_queue, self.kafka_hash_q, self.duration_lock))

		# set all process daemons
		self.my_logger.info('Setting all processes to daemon=True')
		self.audio_process.daemon = True
		self.hash_process.daemon = True
		self.posting_process.daemon = True
		self.streaming_process.daemon = True


		# clean up ephemeral recordings from previous containers
		try:
			self.wav_check(self.post_queue)
		except Exception as e:
			self.my_logger.error(e)


	def update_state(self, new_state):
		self._state = new_state
		print(f"\n[update_state]  NEW STATE: {new_state}")


	"""
		Audio Thread Methods
	"""

	def get_audio(self, frame_q, p, duration_lock, calibration_flag, calibration_lock):
		self.my_logger.info('Audio Process Successfully Started')
		self.my_logger.info('Recording...')
		self.update_state("Recording")
		calibrating = False

		while True:
			if self.duration_update:
				self.update_state("Changing recording duration")
				self.my_logger.info('get_audio: Acquiring recording duration lock...')
				duration_lock.acquire()  # blocking
				self.my_logger.info('get_audio: Recording duration lock acquired. Opening audio stream.')

				try:
					RECORD_SECONDS = self.file_duration
					self.NCHUNKS = int(RECORD_SECONDS * self.RATE / self.CHUNK)
					self.stream = p.open(format=self.FORMAT,
										 channels=self.CHANNELS,
										 rate=self.RATE,
										 input=True,
										 frames_per_buffer=self.CHUNK,
										 input_device_index=self.mic_index)
				finally:
					self.duration_update = False
					duration_lock.release()
			else:
				try:
					if calibration_flag.value:
						self.update_state("Calibrating")
						calibrating = True
						RECORD_SECONDS = self.calibration_duration
						self.NCHUNKS = int(RECORD_SECONDS * self.RATE / self.CHUNK)
						self.my_logger.info("Beginning Calibration")

					# get the start time by using the built in sensorbase method
					start_time = MockSensorBase._get_timestamp()
					frames = []
					for i in range(0, self.NCHUNKS):
						data = self.stream.read(self.CHUNK)
						frames.append(data)

					# join the different subframes together into one big np array
					frame = np.frombuffer(b''.join(frames), dtype=np.int16)
					# get the end time using the sensorbase method
					end_time = MockSensorBase._get_timestamp()
					# put the frame in the frame_q which will handle posting to the CDN
					frame_q.put((frame, start_time, end_time, calibrating))

					if calibrating:
						calibrating = False
						self.my_logger.info("Ending Calibration")
						RECORD_SECONDS = self.file_duration
						self.NCHUNKS = int(RECORD_SECONDS * self.RATE / self.CHUNK)
						with calibration_lock:
							calibration_flag.value = 0
						self.update_state("Recording")

				except Exception as exc_1:
					self.my_logger.error("Error in get_audio: {}".format(exc_1))
					self.stream = p.open(format=self.FORMAT,
										 channels=self.CHANNELS,
										 rate=self.RATE,
										 input=True,
										 frames_per_buffer=self.CHUNK,
										 input_device_index=self.mic_index)


	"""
		Hashing Wav Thread Methods
		Note: This is used in the main thread
	"""

	def frames_to_hash(self, frame_q, post_queue):
		self.my_logger.info('Hash Process Successfully Started')
		calibrate_flag_idx = 3
		while True:
			while not frame_q.empty():
				frame = frame_q.get()
				self.make_wav(frame)
				self.hash_rename(post_queue, frame[calibrate_flag_idx])


	def make_wav(self, frames, output_name='output.wav'):
		"""
		Makes a .wav file with the audio data in frames

		Parameters
		----------
		frames : numpy array of audio data
		output_name : string value for the output name
		Returns
		-------
		Nothing
		"""
		self.my_logger.info('Making wav file...')
		# need to do this to prevent self.start_time and end_time from being overwritten
		self.start_time = frames[1]
		self.end_time = frames[2]
		frames = frames[0]

		wave_file = wave.open(output_name, 'wb')
		wave_file.setnchannels(self.CHANNELS)
		wave_file.setsampwidth(self.p.get_sample_size(self.FORMAT))
		wave_file.setframerate(self.RATE)
		wave_file.writeframes(b''.join(frames))
		wave_file.close()


	def hash_rename(self, post_queue, calibration_flag=False):
		"""
		Changes the name of the output wav to be the computed sha1 hash + .wav
		Puts the new filename along with the hash and file size into the posting queue to get sent to the CDN
		:return:
		"""
		try:
			with open('output.wav', 'rb') as f:
				wav_data = f.read()
				h = hashlib.new('sha1', wav_data)
				# Rename the file to its SHA
				self.filename = h.hexdigest() + '.wav'
			os.rename('output.wav', self.filename)
			self.add_to_post_q(post_queue, self.filename, calibration_flag)
		except Exception as e:
			self.my_logger.error("Exception in hash_rename: {}".format(e))


	def add_to_post_q(self, post_queue, filename, calibration_flag=False):
		filesize = os.path.getsize(self.filename)
		# put all the data into the posting queue as a dictionary for easy unpacking
		post_queue.put({
			"filename": filename,
			"file_size": filesize,
			"sha": filename.split('.')[0],
			"start_t": self.start_time,
			"end_t": self.end_time,
			"calibration": calibration_flag})

		# Clear the start and end timestamps
		self.start_time = ''
		self.end_time = ''


	
	"""
		Posting Thread Method
	"""
	def post_cdn(self, post_queue, kafka_hash_q):
		"""
		checks the post_queue, and parses the dictionary put there by the hash_rename function
		posts the recorded .wav file to the CDN then runs several checks to ensure it was properly placed there
		:return:
		"""
		self.my_logger.info('Posting Process Successfully Started')
		failed_post_attempts = 0

		while True:
			while not post_queue.empty():

				if failed_post_attempts > 4:
					self.my_logger.info('post_cdn incurred too many connection errors -- cancelling operation now.')
					return

				self.my_logger.info('Posting to the CDN')
				# get the message from the post_queue
				message = post_queue.get()
				calibration_flag = message["calibration"]
				# get the associated info from the message
				filename = message["filename"]
				filesize = message["file_size"]
				sha = message["sha"]
				start_time = message["start_t"]
				end_time = message["end_t"]
				
				try:
					files = {'files': open(filename, 'rb')}
					
					if SKIP_POST_CDN:
						os.remove(filename)
						self.my_logger.info("Post to CDN was successful")
						self.my_logger.info("Deleted file: {}".format(filename))

						kafka_hash_q.put({'text': f'{filename}', 'details': {"startTime": str(start_time),
																			 "endTime": str(end_time),
																			 "SHA1": f'{filename}',
																			 "fileSize": str(filesize),
																			 "Room": 'self.room',
																			 "microphone": self.microphone_number,
																			 "calibration_flag": calibration_flag}})
					else:
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
																			 "Room": 'self.room',
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

					failed_post_attempts += 1

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

					failed_post_attempts += 1


	def wav_check(self, post_queue):
		"""This function runs during __init__ to flush out and post any residual .wav files."""
		notify = False  # send a single message instead of spamming for each .wav
		for f in os.listdir():
			if ".wav" in f and "calibration" not in f:
				notify = True
				self.end_time = dt.datetime.fromtimestamp(os.stat(f).st_mtime).strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
				# low priority: TODO: rebuild start time using end time - sample rate * number of frames
				if "output" in f:  # last recording not renamed to SHA1
					f.close()
					self.hash_rename(post_queue)
				else:  # files already renamed to SHA1
					self.add_to_post_q(post_queue, f)
		if notify:
			self.my_logger.warning("Residual .wav(s) found! Files sent to the CDN posting queue...")


	@staticmethod
	def truncate(f, n):
		"""Truncates/pads a float f to n decimal places without rounding"""
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
		# self.set_ready(True)  # calls cnc_base's send_heartbeat()
		pass

	def do_deactivate(self, validated_message):
		# self.set_ready(False)
		self.update_state("Deactivated")


	def shutdown(self):
		self.p.terminate()
		self.streaming_process.join(timeout=5)
		self.posting_process.join(timeout=5)
		self.hash_process.join(timeout=5)
		self.audio_process.join(timeout=5)
		# super(MicrophoneSensor, self).shutdown()


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
				# Debug command to aid in matching the commanded recording length to the actual length of audio recorded
				elif command == 'multiplier':
					if self.sampling_multiplier != command_value:
						self.sampling_multiplier = command_value
						self.update_file_duration(self.file_duration)
					else:
						self.my_logger.warning('Multiplier already set to the requested value.')
			else:  # calibrate
				self.my_logger.info('Received Calibrate Command. Setting do_calibration_flag')
				with self.calibration_lock:
					self.do_calibration_flag.value = 1
		except Exception as e:
			self.my_logger.warning(e)


	def send_acknowledgement(self, command, message_reference):
		# self.send_alert(model.AlertMessageSubtypes.Acknowledgement.value, 6, 2, 'Command Acknowledgement',
		# 				f"Acknowledgement of: {command}", None, [message_reference])
		self.my_logger.info('Acknowledgement Sent')


	def update_file_duration(self, next_duration):
		"""
		Safely update self.file_duration.

		This function should only ever be called when the recording length or multiplier have changed.
		Input validation is performed in the do_parse_control_message() function.
		"""
		self.my_logger.info('update_file_duration: Acquiring recording duration lock...')
		self.duration_lock.acquire()  # blocking
		self.my_logger.info('update_file_duration: Recording duration lock acquired.\nUpdating recording duration...')
		try:
			self.file_duration = self.truncate(next_duration * self.sampling_multiplier, 3)

		except Exception as e:
			self.my_logger.error(f'update_file_duration: Duration failed to update:\n{e}')
		finally:
			self.duration_lock.release()
			self.duration_update = True  # tells the get_audio Process to grab the new duration
			self.my_logger.info('New recording duration set.')



	"""
		Streaming Thread Method
	"""
	def stream_audio(self, post_queue, kafka_hash_q, duration_lock):
		"""  TODO  """
		self.my_logger.info('Streaming Process Successfully Starting')
		cmd = "cvlc -vvv alsa://hw:Microphone --sout-keep --no-sout-video --sout='#transcode{acodec=mpga,ab=128,aenc=ffmpeg,channels=2,samplerate=44100,threads=2}:rtp{mux=ts,dst=239.255.12.42,port=1234,sdp=sap,proto=udp,name=\"YetiAudioStream\"}'"
		self.my_logger.info(cmd)
		self.my_logger.info('stream_audio: Acquiring recording duration lock...')
		duration_lock.acquire()  # blocking
		self.my_logger.info('stream_audio: Recording duration lock acquired. Opening audio stream.')
		os.system(cmd)
		while True:
			pass
			"""
			while not post_queue.empty():
				self.my_logger.info('Streaming .wav audio to the live feed URL')
				# get the message from the post_queue
				message = post_queue.get()
				# get the associated info from the message
				calibration_flag = message["calibration"]
				filename = message["filename"]
				filesize = message["file_size"]
				sha = message["sha"]
				start_time = message["start_t"]
				end_time = message["end_t"]

				try:
					files = {'files': open(filename, 'rb')}

				...

			"""

# -------------------------------------------------------------------------------------

if __name__ == "__main__":
	while True:
		sensor = None
		try:
			room = os.environ.get('ROOM', 'UnknownRoom')
			mic_number = os.environ.get('MIC_NUM', '-1')
			sensor = Microphone(int(mic_number))
			# sensor.start()
			sensor.my_logger.info("Starting Streaming Process")
			sensor.streaming_process.start()
			sensor.my_logger.info('Starting Audio Process')
			sensor.audio_process.start()
			sensor.my_logger.info('Starting Hash Process')
			sensor.hash_process.start()
			sensor.my_logger.info("Starting Posting Process")
			sensor.posting_process.start()
			

			while True:
				if not sensor.kafka_hash_q.empty():
					data = sensor.kafka_hash_q.get()
					if data['details']['calibration_flag']:
						sensor.update_state("Recording_")
						# sensor.send_alert(model.AlertMessageSubtypes.Status.value, 5, 2,
						# 				  'Microphone Calibration CDN Hash',
						# 				  data['text'],
						# 				  data['details'])
						sensor.my_logger.info(f"Calibration Alert sent to Kafka: {data['text']}")
					else:
						# sensor.send_alert(model.AlertMessageSubtypes.Status.value, 5, 2, 'Microphone CDN Hash',
						# 				  data['text'],
						# 				  data['details'])
						sensor.my_logger.info(f"Hash Alert sent to Kafka: {data['text']}")

			# do sensor.shutdown()?
			# break out of the container while loop / raise an exception to restart container?
		except KeyboardInterrupt:
			sensor.do_deactivate('^C received, deactivating...')
			sensor.shutdown()
			sys.exit(0)
		except Exception as exc:
			if sensor is not None:
				sensor.my_logger.error(exc)
			else:
				print(exc)
