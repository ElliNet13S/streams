import time
import json
import os
import cv2
from flask import Flask, Response, render_template, request, redirect, url_for

app = Flask(__name__)

# Path to streams
STREAMS_DIR = './streams'

# Get secret password from environment variable
UPLOAD_PASSWORD = os.getenv('UPLOAD_PASSWORD')

# Check if the password is set, and if not, show a warning message.
if not UPLOAD_PASSWORD:
    print("WARNING: UPLOAD_PASSWORD is not set. File uploads are disabled.")

def load_metadata(stream_name):
    """
    Loads metadata for a given stream from the 'metadata.json' file.

    Args:
        stream_name (str): The name of the stream.

    Returns:
        dict: The parsed metadata from the JSON file, or None if the file is not found.
    """
    metadata_path = os.path.join(STREAMS_DIR, stream_name, 'metadata.json')
    try:
        with open(metadata_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None

def get_video_queue(stream_name):
    """
    Retrieves the current video queue by listing the video files in the stream's 'videos' folder.
    
    Args:
        stream_name (str): The name of the stream.

    Returns:
        list: A list of video filenames in the correct order for playback.
    """
    video_dir = os.path.join(STREAMS_DIR, stream_name, 'videos')
    history_dir = os.path.join(STREAMS_DIR, stream_name, 'history')
    
    videos = sorted([f for f in os.listdir(video_dir) if f.endswith('.mp4')], reverse=False)
    history = set(os.listdir(history_dir))

    return [v for v in videos if v not in history]

def generate_mjpeg_stream(stream_name):
    """
    Generates an MJPEG stream from the videos in the given stream's video queue.

    Args:
        stream_name (str): The name of the stream.

    Yields:
        bytes: JPEG frames in MJPEG format.
    """
    while True:
        video_queue = get_video_queue(stream_name)

        if video_queue:
            video_path = os.path.join(STREAMS_DIR, stream_name, 'videos', video_queue.pop(0))
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            prev_time = time.time()

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                current_time = time.time()
                delta_time = current_time - prev_time
                prev_time = current_time

                if delta_time < (1 / fps):
                    time.sleep((1 / fps) - delta_time)

                _, jpeg = cv2.imencode('.jpg', frame)
                if not _:
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            cap.release()
            history_dir = os.path.join(STREAMS_DIR, stream_name, 'history')
            os.rename(video_path, os.path.join(history_dir, os.path.basename(video_path)))

        offline_video_path = os.path.join(STREAMS_DIR, stream_name, 'offline.mp4')
        cap = cv2.VideoCapture(offline_video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        prev_time = time.time()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            current_time = time.time()
            delta_time = current_time - prev_time
            prev_time = current_time

            if delta_time < (1 / fps):
                time.sleep((1 / fps) - delta_time)

            _, jpeg = cv2.imencode('.jpg', frame)
            if not _:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

        cap.release()

        if not video_queue:
            continue

@app.route('/<stream_name>/video_feed')
def video_feed(stream_name):
    """
    Route that serves the MJPEG stream for a specific stream.

    Args:
        stream_name (str): The name of the stream.

    Returns:
        Response: An MJPEG stream response.
    """
    return Response(generate_mjpeg_stream(stream_name),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/<stream_name>')
def stream_page(stream_name):
    """
    Route for displaying the stream page, with metadata.

    Args:
        stream_name (str): The name of the stream.

    Returns:
        render_template: The stream page with metadata.
    """
    metadata = load_metadata(stream_name)
    stream_title = metadata["name"] if metadata else stream_name
    return render_template('stream_page.html', stream_name=stream_name, stream_title=stream_title)

@app.route('/')
def index():
    """
    Route for the homepage, listing all available streams.

    Returns:
        render_template: The homepage with a list of streams and metadata.
    """
    streams = [d for d in os.listdir(STREAMS_DIR) if os.path.isdir(os.path.join(STREAMS_DIR, d))]
    
    stream_metadata = {}
    for stream in streams:
        metadata = load_metadata(stream)
        if metadata:
            stream_metadata[stream] = metadata["name"]
        else:
            stream_metadata[stream] = stream

    return render_template('index.html', stream_metadata=stream_metadata)

@app.route('/<stream_name>/upload', methods=['GET', 'POST'])
def upload(stream_name):
    """
    Route for handling file uploads to a specific stream.

    Args:
        stream_name (str): The name of the stream.

    Returns:
        str: A message indicating success or failure.
    """
    if not UPLOAD_PASSWORD:
        return "UPLOAD_PASSWORD environment variable is not set. Uploads are disabled.", 403

    if request.method == 'POST':
        password = request.form.get('password')
        if password != UPLOAD_PASSWORD:
            return "Invalid password!", 403

        file = request.files.get('file')
        if file and file.filename.endswith('.mp4'):
            filename = secure_filename(file.filename)
            upload_path = os.path.join(STREAMS_DIR, stream_name, 'videos', filename)
            file.save(upload_path)
            return redirect(url_for('stream_page', stream_name=stream_name))

        return "Invalid file format. Only .mp4 files are allowed.", 400

    return render_template('upload_page.html', stream_name=stream_name)

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5000)
