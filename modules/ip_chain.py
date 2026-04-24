import cv2
import numpy as np

def ip_chain(img_orig, filters, overflow):

	if (len(filters) == 0):
		return img_orig
	elif len(filters) == 1:
		img = filters[0].filter(img_orig)
		return img

	img = cv2.cvtColor(img_orig, cv2.COLOR_BGR2GRAY)

	for i in range(len(filters)):
		img = filters[i].filter(img)
	
	if len(img.shape) != 3:
		img = cv2.merge([img,img,img])
	
	if overflow:
		final_img = img*cv2.bitwise_not(img_orig)
	else:
		cv2.normalize(img, img, 0, 255, cv2.NORM_MINMAX)
		final_img = img.astype(np.uint8)

	return final_img