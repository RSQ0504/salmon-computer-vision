from pyARIS import pyARIS
from tqdm import tqdm
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import skimage.measure
import cv2


source_file = '2020-05-27_071000.aris'


def get_echogram(aris_data, frame):
    num_frame = aris_data.FrameCount - 1
    echogram = np.array([])
    for i in tqdm(range(0, num_frame)):  # aris_data.FrameCount - 1
        _frame = pyARIS.FrameRead(aris_data, i)
        echogram = np.append(echogram, get_vertical_line(_frame))
    echogram = echogram.reshape(num_frame, frame.frame_data.shape[0])
    echogram = np.rot90(echogram)
    return echogram


def get_vertical_line(frame):
    vline = np.array([])
    for row in range(frame.frame_data.shape[0]):
        val = np.array(frame.frame_data[row]).max()
        vline = np.append(vline, val)
    return vline


def save_echogram_as_img(echogram, filename="./result/my_echogram.png"):
    im = Image.fromarray(echogram).convert('RGB')
    im.save(filename)


def read_echogram_img(filename):
    return cv2.imread(filename)  # RGB
    # Convert it to depth 1 matrix
    # im_frame = Image.open(filename).convert('L')
    # return np.array(im_frame.getdata()).reshape(im_frame.size[1], im_frame.size[0])


def avg_pooling(frame, n, m):
    return skimage.measure.block_reduce(frame, (n, m), np.mean)


def avg_convolve(frame, n, m):
    kernel = np.ones((n, m), np.float32) / (n * m)
    return cv2.filter2D(frame, -1, kernel)


def edge_detection(frame):
    kernel = np.array([[-1, -1, -1],
                    [-1, 8, -1],
                    [-1, -1, -1]])
    return cv2.filter2D(frame, -1, kernel)


def bg_sub(echogram):
    sub = cv2.createBackgroundSubtractorMOG2(
                history=100,
                varThreshold=20,
                detectShadows=False
            )

    # Iterate vertical lines on echogram
    bgsub_eg = np.array([])
    for col in range(echogram.shape[1]):
        bgsub_vline = sub.apply(echogram[:,col])
        bgsub_eg = np.append(bgsub_eg, bgsub_vline)
    bgsub_eg = bgsub_eg.reshape(echogram.shape[1], echogram.shape[0])
    bgsub_eg = np.rot90(bgsub_eg)
    return bgsub_eg


if __name__ == '__main__':
    aris_data, frame = pyARIS.DataImport(source_file)
    echogram = get_echogram(aris_data, frame)
    bgsub_eg = bg_sub(echogram)
    save_echogram_as_img(bgsub_eg)
    plt.imshow(bgsub_eg, cmap='gray', vmin=0, vmax=255)
    plt.show()

    # echogram = read_echogram_img("my_echogram.png")
    # # echogram = edge_detection(echogram)
    # echogram = avg_convolve(echogram, 5, 5)
    # # echogram = avg_pooling(echogram, 5, 5)
    # plt.imshow(echogram, cmap='gray', vmin=0, vmax=255)
    # plt.show()
