import cv2
import numpy as np

# each filter has a filter method; imagine they inherit from an interface

class GaussianFilter:

	def __init__(self, ksize=21):
		
		self.__ksize = ksize
		self.__sigma = 1
		
	def filter(self, image):
		return cv2.GaussianBlur(image, (self.__ksize, self.__ksize), self.__sigma)

		
class MedianFilter:

	def __init__(self, ksize = 21):
		
		self.__kernel_size = ksize
		
	def filter(self, image : np.ndarray):
		return cv2.medianBlur(image, self.__kernel_size)
	
class ChannelRoll: 
	# Convert from BGR to:
	# 0: BGR -> BGR
	# 1: BGR -> BRG
	# 2: BGR -> RBG
	# 3: BGR -> RGB
	# 4: BGR -> GRB
	# 5: BGR -> GBR
	def __init__(self, option : int):
		self.option = option
		if self.option not in range(6):
			self.option = self.option % 6
	
	def filter(self, img : np.ndarray):
		if len(img.shape) != 3:
			img = cv2.merge([img,img,img])
		
		reorder_list = [0,1,2]
		if self.option == 0:
			return img
		elif self.option == 1:
			reorder_list = [0,2,1]
		elif self.option == 2:
			reorder_list = [2,0,1]
		elif self.option == 3:
			reorder_list = [2,1,0]
		elif self.option == 4:
			reorder_list = [1,2,0]
		elif self.option == 5:
			reorder_list = [1,0,2]
		
		reorder_img = img[:,:, reorder_list]
		return reorder_img.copy()
	
class NormalizeOverflow:
	def __init__(self, factor, offset=0):
		self.__factor = int(factor)
		self.offset = int(offset)
	
	def filter(self, img):
		img -= self.offset
		cv2.normalize(img, img, 0, 255, cv2.NORM_MINMAX)
		img = img.astype(np.uint8)
		if len(img.shape) == 1:
			img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
		
		final_img = (img//self.__factor)#*cv2.bitwise_not(img_orig)
		return final_img