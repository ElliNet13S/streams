import os
import json
import cv2
from flask import Flask, Response, send_file, render_template_string, request, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_PASSWORD'] = 'changeme'  # Change this to a secure password

BASE_DIR = './streams'

TEMPLATE_INDEX = '''
<!DOCTYPE html>
<html>
<head>
  <title>Streams</title>
  <style>
    body { font-family: sans-serif; margin: 2em; }
  </style>
</head>
<body>
<h1>Available Streams</h1>
<ul>
{% for stream in streams %}
  <li><a href="/{{ stream }}">{{ metadata[stream] }}</a> - {{ 'Online' if online[stream] else 'Offline' }}</li>
{% endfor %}
</ul>
<a href="/upload">Upload a Video (Admin)</a>
</body>
</html>
'''

TEMPLATE_STREAM = '''
<!DOCTYPE html>
<html>
<head>
  <title>{{ stream_title }}</title>
  <style>
    html, body { margin: 0; padding: 0; height: 100%; }
    img { width: 100%; height: 100%; object-fit: contain; }
  </style>
</head>
<body>
<img src="/{{ stream_name }}/mjpeg">
</body>
</html>
'''

TEMPLATE_UPLOAD = '''
<!DOCTYPE html>
<html>
<head>
  <title>Upload Video</title>
  <style>
    body { font-family: sans-serif; margin: 2em; }
  </style>
</head>
<body>
<h1>Upload a Video</h1>
<form method="POST" enctype="multipart/form-data">
  Password: <input type="password" name="password"><br><br>
  Stream:
  <select name="stream">
    {% for stream in streams %}
    <option value="{{ stream }}">{{ metadata[stream] }}</option>
    {% endfor %}
  </select><br><br>
  File: <input type="file" name="file"><br><br>
  <input type="submit" value="Upload">
</form>
</body>
</html>
'''

def get_streams():
    return [s for s in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, s))]

def get_next_video_path(stream_path):
    video_dir = os.path.join(stream_path, 'videos')
    files = sorted(os.listdir(video_dir))
    return os.path.join(video_dir, files[0]) if files else None

def move_to_history(stream_path, video_file):
    history_dir = os.path.join(stream_path, 'history')
    os.makedirs(history_dir, exist_ok=True)
    os.rename(video_file, os.path.join(history_dir, os.path.basename(video_file)))

def load_metadata():
    meta = {}
    for s in get_streams():
        path = os.path.join(BASE_DIR, s, 'metadata.json')
        try:
            with open(path) as f:
                data = json.load(f)
                meta[s] = data.get('name', s)
        except:
            meta[s] = s
    return meta

@app.route('/')
def index():
    streams = get_streams()
    online = {}
    for s in streams:
        path = os.path.join(BASE_DIR, s, 'videos')
        online[s] = bool(os.listdir(path))
    metadata = load_metadata()
    return render_template_string(TEMPLATE_INDEX, streams=streams, online=online, metadata=metadata)

@app.route('/<stream_name>')
def stream_page(stream_name):
    metadata_path = os.path.join(BASE_DIR, stream_name, 'metadata.json')
    stream_title = stream_name
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            meta = json.load(f)
            stream_title = meta.get('name', stream_name)
    return render_template_string(TEMPLATE_STREAM, stream_name=stream_name, stream_title=stream_title)

@app.route('/<stream_name>/mjpeg')
def mjpeg_stream(stream_name):
    stream_path = os.path.join(BASE_DIR, stream_name)
    next_video = get_next_video_path(stream_path)

    if not next_video:
        return "Stream offline", 404

    cap = cv2.VideoCapture(next_video)

    def generate():
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        cap.release()
        move_to_history(stream_path, next_video)

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    streams = get_streams()
    metadata = load_metadata()
    if request.method == 'POST':
        password = request.form.get('password')
        if password != app.config['UPLOAD_PASSWORD']:
            return "Unauthorized", 403

        stream = request.form.get('stream')
        file = request.files['file']
        if stream and file:
            filename = secure_filename(file.filename)
            save_path = os.path.join(BASE_DIR, stream, 'videos', filename)
            file.save(save_path)
            return redirect(url_for('index'))

    return render_template_string(TEMPLATE_UPLOAD, streams=streams, metadata=metadata)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
