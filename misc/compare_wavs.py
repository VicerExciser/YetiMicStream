import os
from time import sleep

class WAV():
	def __init__(self, name, details_dict):
		self.name = name 
		self.details = details_dict
		
	def get_info(self):
		print(f"{'='*40}\nFilename:\t{self.name}")
		print(f"\tChannels:\t{self.details['chan']}")
		print(f"\tBitrate:\t{self.details['ab']} kBit/s")
		print(f'{"="*40}\n')
		
	def play(self):
		self.get_info()
		os.system(f"omxplayer -o local {self.name}")
		

wav_filenames = [
	"noab_aencffmpeg_1channel_stream_capture0.wav",
	"noab_aencffmpeg_stream_capture1.wav",
	"ab128_aencffmpeg_1channel_stream_capture0.wav",
	"ab128_aencffmpeg_stream_capture2.wav",
	"ab256_aencffmpeg_1channel_stream_capture0.wav",
	"ab256_aencffmpeg_2channels_stream_capture0.wav",
]
		
if __name__ == "__main__":
	clips = [WAV(wav_filenames[0], {"ab":'(None/auto)', "chan":1})]
	clips.append(WAV(wav_filenames[1], {"ab":'(None/auto)', "chan":2}))
	clips.append(WAV(wav_filenames[2], {"ab":128, "chan":1}))
	clips.append(WAV(wav_filenames[3], {"ab":128, "chan":2}))
	clips.append(WAV(wav_filenames[4], {"ab":256, "chan":1}))
	clips.append(WAV(wav_filenames[5], {"ab":256, "chan":2}))
	
	for i,clip in enumerate(clips):
		c = input(f"Press enter to sample clip #{i}:\n")
		clips[i].play()
		sleep(1)
