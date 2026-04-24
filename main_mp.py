import cv2
import multiprocessing as mp
from multiprocessing import shared_memory
import numpy as np
import modules.ip_chain as ip_chain
import modules.filters as filters
import time
import mido
import pygame as pg
import configparser
from modules.controller import Controller
import math

# keyboard controls:

# VIDEO INPUT
	# tab    : increment video bank
	# Start  : go to next video bank
	# Select : go to prev video bank
	# DLeft / shft : go to prev video inside a given bank
	# DRight / ctrl : go to next video inside a given bank
	# [    : decrease framerate
	# ]    : increase framerate
	# =    : reset framerate to 15
	# LT   : change framerate between 15-30fps
# FILTERS
	# DUp / q  : ip chain mode back
	# DDn / a  : ip chain mode front
	# A / s    : toggle filter change based on midi beat detection
	# LS       : Change brightness (LSY) and contrast (LSX)
# VISUALS MODE
	# X / w    : toggle blending
	# Y / o    : toggle overflow
	# RSB / x  : rgb channel roll increment
	# B / d    : toggle rgb channel roll based on midi beat detection
	# RS       : Change channel roll based on stick angle (every 60 degrees)
# AUDIO REACT
	# z    : toggle audio reactivity
	# ;    : reduce audio reactivity factor
	# '    : increase audio reactivity factor
	# /    : reset audio reactivity to lowest factor
	# RT   : change audio reactivity factor between (1-32)/32
# esc  : quit

# -----------------------------
# Config
# -----------------------------
WIDTH = 1280
HEIGHT = 720
CHANNELS = 3
FRAME_SHAPE = (HEIGHT, WIDTH, CHANNELS)
FRAME_NBYTES = HEIGHT * WIDTH * CHANNELS
META_LENGTH = 18

FILTER_BEATMODE_CHG_FRQ = 16 # filter changes every N beats
MAX_FILTERS = 2 # total num of filters (including no filter)

MAX_INPUT_MODES = 3 # camera at 0 + 8 banks of video input
CHANNEL_ROLL_FREQ = 4 # change rgb channel roll every n beats
MAX_CHANNEL_ROLLS = 6*CHANNEL_ROLL_FREQ # for rgb channel rolling

INPUT_DEFAULT_FRAMERATE = 15

MAX_AUD_REACT_FACTOR = 32

## Meta Shared Variable Manager

class SharedVariables:

	def __init__(self, buffer, buf_length):
		self.meta = buffer
		self.length = buf_length
		self.var_dict = {
			'stop' : 0,                     # global stop flag 
			'input_seq' : 1,                # input sequence tag for each frame
			'output_seq' : 2,               # output sequence tag for each frame
			'aud_react_number' : 3,         # audio reactivity integer (out of 127)
			'aud_react_factor' : 4,         # multiplication factor of aud react integer
			'beat_detect_togl' : 5,         # to change filter mode based on beat
			'curr_bpm' : 6,                 # song bpm reported by mixxx
			'filter_mode_ctr' : 7,          # whichth filter is currently active (out of 7)
			'input_bank_ctr' : 8,           # which video bank is currently being read from
			'input_videos_max' : 9,         # how many max videos in current video bank
			'input_video_ctr' : 10,         # which video inside of bank is being read
			'input_framerate' : 11,         # self explanatory
			'blend_togl' : 12,              # to use blend filter or not 
			'overflow_togl' : 13,           # to overflow or not
			'rgb_channel_roll_ctr' : 14,    # whichth rgb channel roll is being used 
			'rgb_channel_roll_togl' : 15,   # to change rgb channel roll based on beat 
			'brightness' : 16,              # current brightness modifier
			'contrast' : 17                 # current contrast modifier
		}

	def get(self, varname : str):
		if varname in self.var_dict:
			return self.meta[self.var_dict[varname]]
		else:
			raise KeyError("Invalid key for meta array.")
	
	def set(self, varname : str, value):
		if varname in self.var_dict:
			self.meta[self.var_dict[varname]] = value
		else:
			raise KeyError("Invalid key for meta array.")
	
	def toggle(self, varname : str):
		if varname in self.var_dict and varname.endswith('togl'):
			self.meta[self.var_dict[varname]] = not self.meta[self.var_dict[varname]]
		
	def filter_mode_change(self, change):
		filter_mode_ctr = self.meta[self.var_dict['filter_mode_ctr']]
		self.meta[self.var_dict['filter_mode_ctr']] = (filter_mode_ctr + change) % \
			(FILTER_BEATMODE_CHG_FRQ*MAX_FILTERS)
	
	def rgb_channel_roll_change(self, change):
		rgb_channel_roll_ctr = self.meta[self.var_dict['rgb_channel_roll_ctr']]
		self.meta[self.var_dict['rgb_channel_roll_ctr']] = (rgb_channel_roll_ctr + change) % MAX_CHANNEL_ROLLS
	
	def input_video_change(self, change):
		input_video_ctr = self.meta[self.var_dict['input_video_ctr']]
		input_videos_max = self.meta[self.var_dict['input_videos_max']]
		self.meta[self.var_dict['input_video_ctr']] = (input_video_ctr + change) % input_videos_max
	
	def input_bank_change(self, change):
		input_bank_ctr = self.meta[self.var_dict['input_bank_ctr']]
		self.meta[self.var_dict['input_bank_ctr']] = (input_bank_ctr + change) % MAX_INPUT_MODES

# -----------------------------
# Shared memory helpers
# -----------------------------
def open_frame(name):
	shm = shared_memory.SharedMemory(name=name)
	arr = np.ndarray(FRAME_SHAPE, dtype=np.uint8, buffer=shm.buf)
	return shm, arr

def open_meta(name):
	shm = shared_memory.SharedMemory(name=name)
	arr = np.ndarray((META_LENGTH,), dtype=np.int64, buffer=shm.buf)
	meta_handler = SharedVariables(arr, META_LENGTH)
	return shm, meta_handler

def read_midi(meta_name):

	meta_shm, meta_handler = open_meta(meta_name)
	meta_handler.set('curr_bpm', 120) # default amt

	with mido.open_input() as inport:
		for msg in inport:
			if meta_handler.get('stop'):
				break   
			if (msg.type == 'note_on'):
				if msg.note == 68:
					vel = int(msg.velocity)

					# audio reactive element, constantly reports
					meta_handler.set('aud_react_number', vel)
						
				if msg.note == 0x32 and int(msg.velocity) == 100:
					# beat is on
					
					if meta_handler.get('beat_detect_togl'): # iff beat detection has been toggled on
						# change beat mode
						meta_handler.filter_mode_change(1)
					
					if meta_handler.get('rgb_channel_roll_togl'):
						meta_handler.rgb_channel_roll_change(1)
				
				if (msg.note == 52):
					# mixxx uses an offset of 50 from the real bpm to manage the 0-127 constraint
					# bpm is reported 25 times a second
					meta_handler.set('curr_bpm', int(msg.velocity)+50)
				
				if (msg.note == 48):
					# deck change triggers a video source change
					meta_handler.input_video_change(1)
		
	meta_shm.close()

def ipchain_process(input_name, output_name, meta_name):

	in_shm, input_frame = open_frame(input_name)
	out_shm, output_frame = open_frame(output_name)
	meta_shm, meta_handler = open_meta(meta_name)

	last_seen = -1
	mosh_buffer = None
	frame_counter = 0

	while True:
		
		if meta_handler.get('stop'):
			break
		
		# check if input sequence has been updated
		seq = int(meta_handler.get('input_seq'))

		if seq == last_seen:
			time.sleep(0.001)
			continue

		beat_mode = int(meta_handler.get('filter_mode_ctr'))//FILTER_BEATMODE_CHG_FRQ
		audio_reactivity = int(meta_handler.get('aud_react_number'))/127
		rgb_channel_roll_ctr = meta_handler.get('rgb_channel_roll_ctr')
		blend_togl = meta_handler.get('blend_togl')
		curr_bpm = meta_handler.get('curr_bpm')
		overflow_togl = meta_handler.get('overflow_togl')
		
		aud_react_factor = meta_handler.get('aud_react_factor')

		if meta_handler.get('aud_react_factor') <= 0:
			aud_react_factor = 1
			meta_handler.set('aud_react_factor', 1)
		elif meta_handler.get('aud_react_factor') > MAX_AUD_REACT_FACTOR:
			aud_react_factor = MAX_AUD_REACT_FACTOR
			meta_handler.set('aud_react_factor', MAX_AUD_REACT_FACTOR)
			
		audio_reactivity = 1 - audio_reactivity*(aud_react_factor/MAX_AUD_REACT_FACTOR)

		if beat_mode == 1:
			ksize = int(audio_reactivity*40)
			if ksize % 2 == 0:
				ksize += 1
			divide_factor = int(20 + audio_reactivity*30)
			filter_list = [
				filters.GaussianFilter(ksize),
				filters.MedianFilter(ksize),
				filters.NormalizeOverflow(divide_factor)
			]
		else:
			# datamosh / blend frames
			filter_list = []
		
		frame = input_frame.copy()
		frame_counter += 1

		processed = ip_chain.ip_chain(frame, filter_list, overflow_togl)

		channel_roller = filters.ChannelRoll(rgb_channel_roll_ctr//CHANNEL_ROLL_FREQ)
		processed = channel_roller.filter(processed)
		
		if blend_togl and not (mosh_buffer is None):

			current = processed

			if current.dtype != np.uint8:
				current = current.astype(np.uint8)

			# Tunables
			refresh_interval = curr_bpm//2        # force reset every N frames
			blend_strength = 0.8 + 0.1*(audio_reactivity)  # how much old frame persists

			# Periodically refresh to avoid infinite sludge
			if frame_counter % refresh_interval == 0:
				mosh_buffer = current.copy()
			else:
				if beat_mode == 0:
					current += mosh_buffer

				mosh_buffer = cv2.addWeighted(
					mosh_buffer, blend_strength, current, 1.0 - blend_strength, 0
				)

			processed = mosh_buffer
		
		elif blend_togl and (mosh_buffer is None):
			mosh_buffer = processed.copy()

		output_frame[:] = processed
		
		# update output sequence
		meta_handler.set('output_seq', seq)
		last_seen = seq
	
	in_shm.close()
	out_shm.close()
	meta_shm.close()

def video_reader(input_name, meta_name, input_mode_count):

	meta_shm, meta_handler = open_meta(meta_name)
	in_shm, input_frame = open_frame(input_name)

	cap = None

	config = configparser.ConfigParser()
	config.read("config.ini")

	video_list = [0]
	cameras_list = [0,4]
	
	if input_mode_count == 0:

		cameras_list = config["cameras"]["numbers"]
		cameras_list = cameras_list.split('\n')

		meta_handler.set('input_videos_max', len(cameras_list))
		meta_handler.set('input_video_ctr', 0)

		print("camera list", cameras_list)
	else:

		video_banks = config["video_banks"]

		if input_mode_count == 1:
			video_list = video_banks["bank1"]
		elif input_mode_count == 2:
			video_list = video_banks["bank2"]
		video_list = video_list.split('\n')

		print("video list", video_list)

		meta_handler.set('input_videos_max', len(video_list))
		meta_handler.set('input_video_ctr', 0)

	while True:

		if meta_handler.get('stop') or meta_handler.get('input_bank_ctr') != input_mode_count:
			break

		video_bank_index = meta_handler.get('input_video_ctr')

		if video_bank_index < meta_handler.get('input_videos_max') and input_mode_count != 0:
				video_name = video_list[video_bank_index]
				cap = cv2.VideoCapture(video_name)
		else:
			# cap = cv2.VideoCapture(0)
			video_name = 0
			
		
		if input_mode_count == 0:
			camera_list_index = meta_handler.get('input_video_ctr')
			video_name = int(cameras_list[camera_list_index])
			
			cap = cv2.VideoCapture(video_name, cv2.CAP_V4L2)
			cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
			cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
			cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
		
		while True:

			if meta_handler.get('stop') or \
				meta_handler.get('input_bank_ctr') != input_mode_count or \
				meta_handler.get('input_video_ctr') != video_bank_index:
				break

			ret, frame = cap.read()
			
			if ret:

				if frame.shape[:2] != (HEIGHT, WIDTH):
					frame = cv2.resize(frame, (WIDTH, HEIGHT))
				if len(frame.shape) != 3:
					frame = cv2.merge([frame,frame,frame])

				input_frame[:] = frame

				input_seq = meta_handler.get('input_seq')
				meta_handler.set('input_seq', input_seq + 1)
			
			else:
				if input_mode_count != 0 :
					cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

			time.sleep(1/meta_handler.get('input_framerate'))

	in_shm.close()
	meta_shm.close()

	cap.release()


def input_process(input_name, meta_name):
	meta_shm, meta_handler = open_meta(meta_name)

	while True:

		if meta_handler.get('stop'):
			break

		video_reader(input_name, meta_name, meta_handler.get('input_bank_ctr'))

	meta_shm.close()

class Locker:
	def __init__(self, lock_list):
		self.lock_list = lock_list
	
	def lock(self, index):
		self.lock_list[index] = True
	def unlock(self, index):
		self.lock_list[index] = False
	def toggle(self, index):
		self.lock_list[index] = not self.lock_list[index]
	def is_locked(self, index):
		return self.lock_list[index]

class ChannelRoller:
	def __init__(self, max_channel_rolls, x=1, y=0):
		self.max_channel_rolls = max_channel_rolls
		self.x = x
		self.y = y
		self.angle = 0
		self.__update_angle()
	
	def __update_angle(self):
		angle = math.atan2(self.y, self.x)
		if (angle < 0):
			angle = 2*math.pi + angle
		if (angle > 2*math.pi):
			angle = 2*math.pi - angle
		self.angle = angle
	
	def update_x(self, x):
		self.x = x
		self.__update_angle()
	def update_y(self, y):
		self.y = y
		self.__update_angle()
	def get_channel_roll(self):
		return int(self.angle/((2*math.pi)/self.max_channel_rolls))

def controller_input_process(meta_name):

	meta_shm, meta_handler = open_meta(meta_name)

	ctrl = Controller(0, deadzone=0.08, auto_init=False)

	# list obj that checks if framerate and aud react are locked
	locker = Locker([False, False])
	channel_roller = ChannelRoller(6)

	def on_a_press(c: Controller, button: str) -> None:
		meta_handler.toggle('beat_detect_togl')

	def on_y_press(c: Controller, button: str) -> None:
		meta_handler.toggle('overflow_togl')

	def on_b_press(c: Controller, button: str) -> None:
		meta_handler.toggle('rgb_channel_roll_togl')

	def on_x_press(c: Controller, button: str) -> None:
		meta_handler.toggle('blend_togl')

	def on_dup_press(c: Controller, button: str) -> None:
		meta_handler.filter_mode_change(-FILTER_BEATMODE_CHG_FRQ)

	def on_ddown_press(c: Controller, button: str) -> None:
		meta_handler.filter_mode_change(FILTER_BEATMODE_CHG_FRQ)

	def on_dleft_press(c: Controller, button: str) -> None:
		meta_handler.input_video_change(-1)

	def on_dright_press(c: Controller, button: str) -> None:
		meta_handler.input_video_change(1)

	def on_lsb_press(c: Controller, button: str) -> None:
		meta_handler.rgb_channel_roll_change(CHANNEL_ROLL_FREQ)

	def on_lb_press(c: Controller, button: str) -> None:
		# toggle framerate lock
		locker.toggle(0)

	def on_rb_press(c: Controller, button: str) -> None:
		# toggle audio reactivity factor lock
		locker.toggle(1)

	def on_start_press(c: Controller, button: str) -> None:
		meta_handler.input_bank_change(1)
	
	def on_select_press(c: Controller, button: str) -> None:
		meta_handler.input_bank_change(-1)

	# axis mappings

	def on_left_x(c: Controller, axis_name: str, value: float) -> None:
		meta_handler.set('contrast', 127 + int(value*127))

	def on_left_y(c: Controller, axis_name: str, value: float) -> None:
		meta_handler.set('brightness', 127 + int(value*127))
	
	def on_left_trigger(c: Controller, axis_name: str, value: float) -> None:
		if not locker.is_locked(0):
			meta_handler.set('input_framerate', 15 + int(15*value))
	
	def on_right_x(c: Controller, axis_name: str, value: float) -> None:
		channel_roller.update_x(value)
		meta_handler.set('rgb_channel_roll_ctr', CHANNEL_ROLL_FREQ*channel_roller.get_channel_roll())
		
	def on_right_y(c: Controller, axis_name: str, value: float) -> None:
		channel_roller.update_y(value)
		meta_handler.set('rgb_channel_roll_ctr', CHANNEL_ROLL_FREQ*channel_roller.get_channel_roll())

	def on_right_trigger(c: Controller, axis_name: str, value: float) -> None:
		if not locker.is_locked(1):
			meta_handler.set('aud_react_factor', 1 + int((MAX_AUD_REACT_FACTOR-1)*value))

	ctrl.map_button_press("a", on_a_press)
	ctrl.map_button_press("y", on_y_press)
	ctrl.map_button_press("x", on_x_press)
	ctrl.map_button_press("b", on_b_press)
	ctrl.map_button_press("left_stick", on_lsb_press)
	# ctrl.map_button_press("right_stick", on_rsb_press)
	ctrl.map_button_press("left_shoulder", on_lb_press)
	ctrl.map_button_press("right_shoulder", on_rb_press)
	ctrl.map_button_press("dpad_up", on_dup_press)
	ctrl.map_button_press("dpad_down", on_ddown_press)
	ctrl.map_button_press("dpad_left", on_dleft_press)
	ctrl.map_button_press("dpad_right", on_dright_press)
	ctrl.map_button_press("back", on_select_press)
	ctrl.map_button_press("start", on_start_press)
	# ctrl.map_button_press("guide", on_menu_press)

	ctrl.map_axis("left_x", on_left_x)
	ctrl.map_axis("left_y", on_left_y)
	ctrl.map_axis("right_x", on_right_x)
	ctrl.map_axis("right_y", on_right_y)
	ctrl.map_axis("left_trigger", on_left_trigger)
	ctrl.map_axis("right_trigger", on_right_trigger)

	try:
		ctrl.open()
	except:
		print("Controller not connected")
		return False
	
	while True:
		
		if meta_handler.get('stop'):
			break

		try:
			ctrl.begin_frame()
		except:
			pass

		for event in pg.event.get():
			try:
				ctrl.process_event(event)
			except:
				pass

		# Optional polling if you want continuously updated state
		try:
			ctrl.poll_live_state()
		except:
			pass
	
	try:
		ctrl.close()
	except:
		pass
	meta_shm.close()

def display_process(output_name, meta_name):

	out_shm, output_frame = open_frame(output_name)
	meta_shm, meta_handler = open_meta(meta_name)

	last_seen = -1

	pg.init()
	pg.display.set_caption("Live Overflow")

	screen_width, screen_height = WIDTH, HEIGHT
	screen = pg.display.set_mode((screen_width, screen_height))#, pg.FULLSCREEN | pg.SCALED)

	disp_image = pg.Surface((screen_width, screen_height))
	output_img = np.zeros(output_frame.shape, output_frame.dtype)
	clock = pg.time.Clock()

	screen.fill((0, 0, 0))

	while True:
		
		if meta_handler.get('stop'):
			break

		seq = int(meta_handler.get('output_seq'))

		if seq != last_seen:
			output_img = np.swapaxes(output_frame.copy(), 0, 1)

		brightness = meta_handler.get('brightness')
		contrast = meta_handler.get('contrast')

		if (brightness != 127 or contrast != 127):
			output_img = cv2.convertScaleAbs(output_img,\
								alpha=(contrast/255) - 2, \
								beta=((2- brightness/127))*50)

		output_img = cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB)

		disp_array = pg.surfarray.pixels3d(disp_image)
		disp_array[:] = output_img
		del disp_array

		for event in pg.event.get():
			if event.type == pg.QUIT:
				meta_handler.set('stop', 1)
			elif event.type == pg.KEYDOWN:
				if event.key == pg.K_ESCAPE:
					meta_handler.set('stop', 1)
				elif event.key == pg.K_q:
					# go to prev IP chain mode
					meta_handler.filter_mode_change(-FILTER_BEATMODE_CHG_FRQ)
				elif event.key == pg.K_a:
					# go to next IP chain mode
					meta_handler.filter_mode_change(FILTER_BEATMODE_CHG_FRQ)
				elif event.key == pg.K_s:
					# toggle midi beat detection on/off
					meta_handler.toggle('beat_detect_togl')
				elif event.key == pg.K_TAB:
					# go to next input video bank
					meta_handler.input_bank_change(1)
				elif event.key == pg.K_LSHIFT:
					# go to next video inside bank
					meta_handler.input_video_change(-1)
				elif event.key == pg.K_LCTRL:
					# go to next video inside bank
					meta_handler.input_video_change(1)
				elif event.key == pg.K_w:
					# toggle frame blending
					meta_handler.toggle('blend_togl')
				elif event.key == pg.K_o:
					# toggle overflow mode
					meta_handler.toggle('overflow_togl')
				elif event.key == pg.K_x:
					# change channel rolls
					meta_handler.rgb_channel_roll_change(CHANNEL_ROLL_FREQ)
				elif event.key == pg.K_d:
					# toggle channel roll on beat detect
					meta_handler.toggle('rgb_channel_roll_togl')
				elif event.key == pg.K_EQUALS:
					# reset framerate
					meta_handler.set('input_framerate', INPUT_DEFAULT_FRAMERATE)
				elif event.key == pg.K_LEFTBRACKET:
					# decrease framerate
					input_framerate = meta_handler.get('input_framerate')
					if input_framerate > 5:
						meta_handler.set('input_framerate', input_framerate - 1)
				elif event.key == pg.K_RIGHTBRACKET:
					# increase framerate
					input_framerate = meta_handler.get('input_framerate')
					if input_framerate < 30:
						meta_handler.set('input_framerate', input_framerate + 1)
				elif event.key == pg.K_SEMICOLON:
					# decrease audio reactive factor
					aud_react_factor = meta_handler.get('aud_react_factor')
					meta_handler.set('aud_react_factor', max(1, aud_react_factor-1))
				elif event.key == pg.K_QUOTE:
					# increase audio reactive factor
					aud_react_factor = meta_handler.get('aud_react_factor')
					meta_handler.set('aud_react_factor', min(MAX_AUD_REACT_FACTOR, aud_react_factor+1))				
				
		screen.blit(disp_image, (0, 0))

		pg.display.flip()
		clock.tick(60)

		input_framerate = meta_handler.get('input_framerate')
		aud_react_factor = meta_handler.get('aud_react_factor')
		beat_detect_togl = meta_handler.get('beat_detect_togl')
		rgb_channel_roll_togl = meta_handler.get('rgb_channel_roll_togl')
		overflow_togl = meta_handler.get('overflow_togl')
		blend_togl = meta_handler.get('blend_togl')

		pg.display.set_caption(f"Live Overflow - FRAME: {input_framerate}/30 - AUD: {aud_react_factor}/{MAX_AUD_REACT_FACTOR} - BEAT: {beat_detect_togl} - CHNRL: {rgb_channel_roll_togl} - OVER: {overflow_togl} - BLEND: {blend_togl}")

	
	pg.quit()
	out_shm.close()
	meta_shm.close()


def main():

	input_shm = shared_memory.SharedMemory(create=True, size=FRAME_NBYTES)
	output_shm = shared_memory.SharedMemory(create=True, size=FRAME_NBYTES)
	meta_shm = shared_memory.SharedMemory(create=True, size=8*META_LENGTH)

	input_arr = np.ndarray(FRAME_SHAPE, dtype=np.uint8, buffer=input_shm.buf)
	output_arr = np.ndarray(FRAME_SHAPE, dtype=np.uint8, buffer=output_shm.buf)
	meta_arr = np.ndarray((META_LENGTH,), dtype=np.int64, buffer=meta_shm.buf)

	input_arr[:] = 0
	output_arr[:] = 0
	meta_arr[:] = 0

	meta_handler = SharedVariables(meta_arr, META_LENGTH)
	meta_handler.set('input_framerate', INPUT_DEFAULT_FRAMERATE)

	capture = mp.Process(target=input_process, args=(input_shm.name, meta_shm.name))
	process = mp.Process(target=ipchain_process,
					  args=(input_shm.name, output_shm.name, meta_shm.name))
	midi = mp.Process(target=read_midi, args=(meta_shm.name,))
	controller = mp.Process(target=controller_input_process, args=(meta_shm.name,))

	capture.start()
	process.start()
	midi.start()
	controller.start()

	display_process(output_shm.name, meta_shm.name)

	capture.join()
	process.join()
	midi.join()

	input_shm.unlink()
	output_shm.unlink()
	meta_shm.unlink()

if __name__ == "__main__":
	mp.set_start_method("spawn", force=True)
	main()
