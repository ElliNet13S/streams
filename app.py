import time
import json
import os
import threading
import cv2
from werkzeug.utils import secure_filename
from flask import Flask, Response, render_template, request, redirect, url_for

app = Flask(__name__)

STREAMS_DIR = './streams'
UPLOAD_PASSWORD = os.getenv('UPLOAD_PASSWORD')

if not UPLOAD_PASSWORD:
    print("WARNING: UPLOAD_PASSWORD is not set. File uploads are disabled.")

def load_metadata(stream_name):
    metadata_path = os.path.join(STREAMS_DIR, stream_name, 'metadata.json')
    try:
        with open(metadata_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading metadata for {stream_name}: {e}")
        return None

def get_video_queue(stream_name):
    video_dir = os.path.join(STREAMS_DIR, stream_name, 'videos')
    history_dir = os.path.join(STREAMS_DIR, stream_name, 'history')
    
    try:
        videos = sorted([f for f in os.listdir(video_dir) if f.endswith('.mp4')])
        history = set(os.listdir(history_dir))
    except FileNotFoundError as e:
        print(f"Error accessing video or history directories for {stream_name}: {e}")
        return []
    
    return [v for v in videos if v not in history]

def resize_frame_with_aspect_ratio(frame, target_width=640, target_height=480):
    h, w = frame.shape[:2]
    aspect_ratio = w / h

    if w > h:
        new_w = target_width
        new_h = int(target_width / aspect_ratio)
    else:
        new_h = target_height
        new_w = int(target_height * aspect_ratio)

    return cv2.resize(frame, (new_w, new_h))

def frame_stream(video_path, stop_event):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = 1.0 / fps if fps > 0 else 1.0 / 30

    while cap.isOpened() and not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            print(f"Reached end of video: {video_path}")
            break

        frame = resize_frame_with_aspect_ratio(frame)

        success, jpeg = cv2.imencode('.jpg', frame)
        if not success:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(frame_interval)

    cap.release()

def generate_mjpeg_stream(stream_name):
    stop_event = threading.Event()
    while True:
        video_queue = get_video_queue(stream_name)

        if video_queue:
            video_filename = video_queue.pop(0)
            video_path = os.path.join(STREAMS_DIR, stream_name, 'videos', video_filename)
            history_path = os.path.join(STREAMS_DIR, stream_name, 'history', video_filename)
            print(f"Switching to video: {video_path}")
            try:
                for frame in frame_stream(video_path, stop_event):
                    yield frame
            finally:
                try:
                    os.rename(video_path, history_path)
                    print(f"Moved to history: {history_path}")
                except Exception as e:
                    print(f"Error moving file to history: {e}")
        else:
            offline_path = os.path.join(STREAMS_DIR, stream_name, 'offline.mp4')
            if not os.path.exists(offline_path):
                print("Error: offline.mp4 not found!")
                time.sleep(2)
                continue

            cap = cv2.VideoCapture(offline_path)
            if not cap.isOpened():
                print(f"Error: Could not open offline video {offline_path}")
                time.sleep(2)
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_interval = 1.0 / fps if fps > 0 else 1.0 / 30

            while cap.isOpened():
                if get_video_queue(stream_name):  # Check for new videos
                    print("New video found, switching from offline.")
                    break

                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame = resize_frame_with_aspect_ratio(frame)

                success, jpeg = cv2.imencode('.jpg', frame)
                if not success:
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                time.sleep(frame_interval)

            cap.release()

@app.route('/<stream_name>/video_feed')
def video_feed(stream_name):
    return Response(generate_mjpeg_stream(stream_name),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/<stream_name>')
def stream_page(stream_name):
    metadata = load_metadata(stream_name)
    stream_title = metadata["name"] if metadata and "name" in metadata else stream_name
    return render_template('stream_page.html', stream_name=stream_name, stream_title=stream_title)

@app.route('/')
def index():
    if not os.path.exists(STREAMS_DIR):
        os.makedirs(STREAMS_DIR)

    streams = [d for d in os.listdir(STREAMS_DIR) if os.path.isdir(os.path.join(STREAMS_DIR, d))]
    stream_metadata = {}
    for stream in streams:
        metadata = load_metadata(stream)
        stream_metadata[stream] = metadata["name"] if metadata and "name" in metadata else stream
    return render_template('index.html', stream_metadata=stream_metadata)

@app.route('/<stream_name>/upload', methods=['GET', 'POST'])
def upload(stream_name):
    if not UPLOAD_PASSWORD:
        return "UPLOAD_PASSWORD environment variable is not set. Uploads are disabled.", 403

    videos_dir = os.path.join(STREAMS_DIR, stream_name, 'videos')
    os.makedirs(videos_dir, exist_ok=True)

    if request.method == 'POST':
        password = request.form.get('password')
        if password != UPLOAD_PASSWORD:
            return "Invalid password!", 403

        file = request.files.get('file')
        if file and file.filename.endswith('.mp4'):
            filename = secure_filename(file.filename)
            upload_path = os.path.join(videos_dir, filename)
            file.save(upload_path)
            return redirect(url_for('stream_page', stream_name=stream_name))
        return "Invalid file format. Only .mp4 files are allowed.", 400

    return render_template('upload_page.html', stream_name=stream_name)

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
