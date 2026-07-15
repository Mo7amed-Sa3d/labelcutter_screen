"""
upload_server.py
------------------
Small Flask server so gcode can be pushed to the machine over WiFi/Ethernet
from any laptop/phone on the same network - no USB stick shuffling. Runs in
a background thread started from main.py; the files panel just re-reads the
gcode directory to pick up new arrivals (a filesystem watch would work too,
but polling every couple seconds is simpler and plenty fast for this).
"""
import os
import threading
from flask import Flask, request, jsonify, render_template_string

UPLOAD_PAGE = """
<!doctype html>
<title>Label Cutter - Upload GCode</title>
<h2>Upload GCode</h2>
<form method=post enctype=multipart/form-data action="/upload">
  <input type=file name=file accept=".gcode,.nc,.txt">
  <input type=submit value=Upload>
</form>
<h3>Files on machine</h3>
<ul>{% for f in files %}<li>{{ f }}</li>{% endfor %}</ul>
"""


class UploadServer:
    def __init__(self, gcode_dir, port=8080):
        self.gcode_dir = gcode_dir
        self.port = port
        os.makedirs(self.gcode_dir, exist_ok=True)
        self.app = Flask(__name__)
        self._register_routes()
        self._thread = None

    def _register_routes(self):
        app = self.app

        @app.route("/", methods=["GET"])
        def index():
            files = sorted(os.listdir(self.gcode_dir))
            return render_template_string(UPLOAD_PAGE, files=files)

        @app.route("/upload", methods=["POST"])
        def upload():
            if "file" not in request.files:
                return jsonify({"error": "no file part"}), 400
            f = request.files["file"]
            if f.filename == "":
                return jsonify({"error": "empty filename"}), 400
            safe_name = os.path.basename(f.filename)
            dest = os.path.join(self.gcode_dir, safe_name)
            f.save(dest)
            return jsonify({"status": "ok", "filename": safe_name})

        @app.route("/files", methods=["GET"])
        def list_files():
            return jsonify(sorted(os.listdir(self.gcode_dir)))

    def start(self):
        self._thread = threading.Thread(
            target=lambda: self.app.run(host="0.0.0.0", port=self.port,
                                         threaded=True, use_reloader=False),
            daemon=True,
        )
        self._thread.start()
