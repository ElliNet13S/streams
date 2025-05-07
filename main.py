import os
import cv2
import time
from flask import Flask, Response, render_template, jsonify
import json

app = Flask(__name__)

# Path to streams
STREAMS_DIR = './streams'

# Helper function to load metadata from stream's metadata.json
def load_metadata(stream_name):
    metadata_path = os.path.join(STREAMS_DIR, stream_name, 'metadata.json')
    try:
        with open(metadata_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None

# Function to get the current video queue
def get_video_queue(stream_name):
    video_dir = os.path.join(STREAMS_DIR, stream_name, 'videos')
    history_dir = os.path.join(STREAMS_DIR, stream_name, 'history')
    
    # Get all video files from 'videos' directory
    videos = sorted([f for f in os.listdir(video_dir) if f.endswith('.mp4')], reverse=False)
    
    # Get history videos (if any, to prevent playing already played videos)
    history = set(os.listdir(history_dir))

    # Remove videos already in history from the video queue
    video_queue = [v for v in videos if v not in history]
    
    return video_queue

# Stream video function
def generate_mjpeg_stream(stream_name):
    while True:
        video_queue = get_video_queue(stream_name)

        # If there are videos left in the queue, play the next one
        if video_queue:
            video_path = os.path.join(STREAMS_DIR, stream_name, 'videos', video_queue.pop(0))
            cap = cv2.VideoCapture(video_path)

            # Get the frames per second (fps) from the video
            fps = cap.get(cv2.CAP_PROP_FPS)
            prev_time = time.time()

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break  # Video ended, move to next video in queue

                # Calculate delta time
                current_time = time.time()
                delta_time = current_time - prev_time
                prev_time = current_time

                # Wait to maintain the correct frame rate using delta time
                if delta_time < (1 / fps):
                    time.sleep((1 / fps) - delta_time)

                _, jpeg = cv2.imencode('.jpg', frame)
                if not _:
                    continue

                # Yield the JPEG image as MJPEG stream
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            # After finishing video, move it to history
            cap.release()
            history_dir = os.path.join(STREAMS_DIR, stream_name, 'history')
            os.rename(video_path, os.path.join(history_dir, os.path.basename(video_path)))

        # If no videos left in the queue, stream the offline video
        offline_video_path = os.path.join(STREAMS_DIR, stream_name, 'offline.mp4')
        cap = cv2.VideoCapture(offline_video_path)

        # Get the frames per second (fps) from the offline video
        fps = cap.get(cv2.CAP_PROP_FPS)
        prev_time = time.time()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break  # Video ended, immediately move to the next video or offline.mp4

            # Calculate delta time
            current_time = time.time()
            delta_time = current_time - prev_time
            prev_time = current_time

            # Wait to maintain the correct frame rate using delta time
            if delta_time < (1 / fps):
                time.sleep((1 / fps) - delta_time)

            _, jpeg = cv2.imencode('.jpg', frame)
            if not _:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

        cap.release()

        # Once offline.mp4 finishes, immediately check the queue and start the next video
        # We call the function again, so it starts fresh with the new video queue
        video_queue = get_video_queue(stream_name)

        # Make sure to only move to offline video if there are no other videos in the queue
        if not video_queue:
            continue

# Video feed route
@app.route('/<stream_name>/video_feed')
def video_feed(stream_name):
    return Response(generate_mjpeg_stream(stream_name),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Stream page route
@app.route('/<stream_name>')
def stream_page(stream_name):
    metadata = load_metadata(stream_name)
    stream_title = metadata["name"] if metadata else stream_name
    return render_template('stream_page.html', stream_name=stream_name, stream_title=stream_title)

# Homepage route (list all streams)
@app.route('/')
def index():
    streams = [d for d in os.listdir(STREAMS_DIR) if os.path.isdir(os.path.join(STREAMS_DIR, d))]
    return render_template('index.html', streams=streams)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
