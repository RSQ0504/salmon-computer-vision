#!/usr/bin/env python3
from .dataloader import DataLoader

import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os
import errno
from threading import Thread, Event, Lock, Condition
import logging

logging.basicConfig( 
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

class VideoSaver(Thread):
    def __init__(self, buffer, folder, stop_event, lock, condition, fps=10.0, resolution=(640, 480)):
        Thread.__init__(self)
        self.buffer = buffer  # This will be a shared queue
        self.folder = folder
        self.stop_event = stop_event  # This will signal when to stop recording
        self.lock = lock  # This will ensure thread-safe access to the buffer
        self.condition = condition
        self.fps = fps
        self.resolution = resolution
        self.daemon = True
        self.gst_out = 'appsrc ! videoconvert ! x264enc ! mp4mux ! filesink location='
        self.gst_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert ! video/x-raw,format=BGRx ! nvvidconv ! nvv4l2h264enc vbv-size=200000 insert-vui=1 ! h264parse ! qtmux ! filesink location="

    def get_output_filename(self, folder):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(folder, f"{os.uname()[1]}_{timestamp}.mp4")
        return filename


    def run(self):
        filename = self.get_output_filename(self.folder)
        out = cv2.VideoWriter(self.gst_writer_str + filename, cv2.CAP_GSTREAMER, 0, self.fps, self.resolution)
        
        c = 0
        # Write the pre-motion frames
        while self.buffer:
            if c % 20 == 0:
                logger.info(f'Saving pre... {c}')
            with self.lock:
                frame = self.buffer.popleft()  # Safely pop from the left of the deque
            out.write(frame)
            c += 1

        c = 0
        # Continue recording until stop_event is set
        while not self.stop_event.is_set():
            with self.condition:
                while not self.buffer and not self.stop_event.is_set():
                    self.condition.wait()  # Wait for a signal that a new frame is available or stop_event is set

                if self.buffer:
                    with self.lock:
                        frame = self.buffer.popleft()
                    if c % 20 == 0:
                        logger.info(f'Saving... {c}')
                    out.write(frame)

            c += 1

        out.release()

class MotionDetector:
    FILENAME = 'filename'
    CLIPS = 'clips'
    def __init__(self, dataloader: DataLoader, save_folder):
        self.dataloader = dataloader
        self.save_folder = save_folder
        self.frame_log = {}

    def detect_motion(self, fg_mask, min_area=500):
        """
        Detect motion in the foreground mask by looking for contours with an area larger than min_area.
        """
        # Find contours in the fg_mask
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2:]

        # Filter out small contours
        for contour in contours:
            if cv2.contourArea(contour) > min_area:
                return True
        return False

    def run(self, algo='MOG2', save_video=True):
        # Motion Detection Params
        bgsub_threshold = 16
        threshold_value = 50 # Increase threshold value to minimize noise
        kernel_size = (7, 7) # Increase kernel size to ignore smaller motions
        morph_iterations = 1 # Run multiple iterations to incrementally remove smaller objects
        min_contour_area = 2000 # Ignore contour objects smaller than this area
        BUFFER_LENGTH = 5 # Number of seconds before motion to keep
        MAX_CLIP_MINS = 2 # Maximum number of minutes per clip


        cur_clip = self.dataloader.next_clip()
        self.frame_log[cur_clip.name] = []

        # Retrieve the FPS of the video stream
        fps = self.dataloader.fps()

        logger.info(f"FPS: {fps}")

        MAX_FRAMES_CLIP = MAX_CLIP_MINS * 60 * fps

        if algo == 'MOG2':
            bgsub = cv2.createBackgroundSubtractorMOG2(varThreshold=bgsub_threshold, detectShadows=False)
        else:
            bgsub = cv2.bgsegm.createBackgroundSubtractorCNT(minPixelStability=int(fps), maxPixelStability=int(fps*60))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, kernel_size)

        warm_up = fps
        buffer_length = int(fps * BUFFER_LENGTH)  # Buffer to save before motion
        buffer = deque(maxlen=buffer_length)
        motion_detected = False

        # Concurrency-safe constructs
        stop_event = Event()
        lock = Lock()
        condition = Condition()

        delay = int(fps * 5) # Number of seconds to delay after motion
        count_delay = 0

        frame_counter = 0
        motion_counter = 0
        frame_start = 0
        for item in self.dataloader.items():
            # Constantly check if save folder exists
            if not os.path.exists(self.save_folder):
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.save_folder)

            frame = item.frame

            if isinstance(frame, str):
                frame = cv2.imread(frame)

            # Apply background subtraction algorithm to get the foreground mask
            fg_mask = bgsub.apply(frame)

            has_motion = False
            if warm_up <= 0:
                # Apply morphological operations to clean up the mask
                for _ in range(morph_iterations):
                    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel) 

                # Apply a threshold to the foreground mask to get rid of noise
                _, fg_mask = cv2.threshold(fg_mask, threshold_value, 255, cv2.THRESH_BINARY)

                # Now detect motion
                has_motion = self.detect_motion(fg_mask, min_area=min_contour_area)
            else:
                warm_up -= 1

            with lock:
                buffer.append(frame)
            with condition:
                condition.notify() # Signal the VideoSaver thread that a new frame is available

            motion_counter += 1

            # Check for motion
            if has_motion:
                count_delay = 0
                if not motion_detected:
                    logger.info("Motion detected.")
                    motion_detected = True
                    motion_counter = 0
                    frame_start = frame_counter
                    if save_video:
                        # Signal that we need to start saving the clip
                        stop_event.clear()
                        video_saver = VideoSaver(buffer, self.save_folder, stop_event, lock, condition, fps=fps, resolution=(frame.shape[1], frame.shape[0]))
                        video_saver.start()
                else:
                    if save_video and motion_counter > MAX_FRAMES_CLIP and not stop_event.is_set():
                        logger.info("Max clip length exceeded. Motion stopped.")
                        logger.info("Stopping recording.")
                        stop_event.set()
                        with condition:
                            condition.notify_all()  # Signal the VideoSaver thread to stop waiting and finish
                        motion_detected = False
            else:
                if count_delay < delay:
                    count_delay += 1
                else:
                    # If motion has stopped and we have a video saver running, set the stop event
                    if motion_detected:
                        logger.info("Delay exceeded. Motion stopped.")
                        self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                        motion_counter = 0
                        if save_video and not stop_event.is_set():
                            logger.info("Stopping recording.")
                            stop_event.set()
                            with condition:
                                condition.notify_all()  # Signal the VideoSaver thread to stop waiting and finish
                            motion_detected = False
                        elif not save_video:
                            motion_detected = False

            frame_counter += 1

        return self.frame_log
