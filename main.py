import os
import time
import cv2
import json
from flask import Flask, Response, render_template, abort

app = Flask(__name__)

# Configuration
BASE_STREAMS_DIR = "./streams"
OFFLINE_VIDEO = "offline.mp4"

# Load metadata
def load_metadata(stream_name):
    metadata_file = os.path.join(BASE_STREAMS_DIR, stream_name, "metadata.json")
    if not os.path.exists(metadata_file):
        return None
    with open(metadata_file, "r") as file:
        return json.load(file)

# Get video files in the directory
def get_video_files(stream_name):
    video_dir = os.path.join(BASE_STREAMS_DIR, stream_name, "videos")
    return [f for f in os.listdir(video_dir) if f.endswith(('.mp4', '.avi', '.mov'))]

# Stream MJPEG video
def generate_mjpeg_stream(stream_name):
    video_files = get_video_files(stream_name)
    if not video_files:
        video_path = os.path.join(BASE_STREAMS_DIR, stream_name, OFFLINE_VIDEO)
    else:
        video_path = os.path.join(BASE_STREAMS_DIR, stream_name, "videos", video_files[0])  # Pick the first video
    
    print(f"Streaming video: {video_path}")

    cap = cv2.VideoCapture(video_path)
    while True:
        ret, frame = cap.read()
        if not ret:
            # Move the video to history and remove it from the video folder
            filename = os.path.basename(video_path)
            video_history_path = os.path.join(BASE_STREAMS_DIR, stream_name, "history", filename)
            os.rename(video_path, video_history_path)

            # Check if there are videos left to play
            video_files = get_video_files(stream_name)
            if video_files:
                video_path = os.path.join(BASE_STREAMS_DIR, stream_name, "videos", video_files[0])
                cap = cv2.VideoCapture(video_path)
            else:
                # No more videos, stream offline video
                video_path = os.path.join(BASE_STREAMS_DIR, stream_name, OFFLINE_VIDEO)
                cap = cv2.VideoCapture(video_path)

        # Encode the frame as MJPEG
        _, jpeg = cv2.imencode('.jpg', frame)
        if jpeg is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
        time.sleep(0.1)

@app.route('/')
def index():
    streams = [d for d in os.listdir(BASE_STREAMS_DIR) if os.path.isdir(os.path.join(BASE_STREAMS_DIR, d))]
    return render_template('index.html', streams=streams)

@app.route('/<stream_name>')
def stream_page(stream_name):
    metadata = load_metadata(stream_name)
    if not metadata:
        abort(404, description="Stream not found.")
    return render_template('stream_page.html', stream_name=stream_name, stream_title=metadata["name"])

@app.route('/<stream_name>/video_feed')
def video_feed(stream_name):
    if not os.path.exists(os.path.join(BASE_STREAMS_DIR, stream_name)):
        abort(404, description="Stream not found.")
    return Response(generate_mjpeg_stream(stream_name),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
