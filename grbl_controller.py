"""
GrblController
---------------
Handles all USB-serial communication with the GRBL 1.1 MCU.

Design notes:
- Runs its own reader thread so the GTK main loop is never blocked on serial IO.
- Uses simple line-based "send, wait for ok/error" streaming (safe and simple -
  fine for label-cutter feedrates; switch to character-counting streaming later
  if you need to push line rate much higher).
- All callbacks fire from the reader/worker threads. The UI layer is
  responsible for marshalling them onto the GTK main loop with GLib.idle_add -
  never touch GTK widgets directly from these callbacks.
"""
import re
import threading
import queue
import time
import serial

STATUS_RE = re.compile(
    r"<(?P<state>\w+)"
    r"(?:\|MPos:(?P<mpos>[-\d.,]+))?"
    r"(?:\|WPos:(?P<wpos>[-\d.,]+))?"
    r"(?:\|FS:(?P<fs>[-\d.,]+))?"
)


class GrblController:
    def __init__(self, port, baud=115200,
                 on_status=None, on_error=None, on_alarm=None, on_line_sent=None):
        self.port_name = port
        self.baud = baud
        self.ser = None
        self._reader_thread = None
        self._worker_thread = None
        self._stop_flag = threading.Event()
        self._job_paused = threading.Event()
        self._job_abort = threading.Event()
        self._job_queue = queue.Queue()
        self._ok_event = threading.Event()
        self._last_error = None
        self._lock = threading.Lock()

        self.on_status = on_status or (lambda s: None)
        self.on_error = on_error or (lambda e: None)
        self.on_alarm = on_alarm or (lambda a: None)
        self.on_line_sent = on_line_sent or (lambda i, n, line: None)

        self.state = "Disconnected"
        self.mpos = (0.0, 0.0, 0.0)
        self.connected = False
        self.job_running = False

    # ---------------------------------------------------------------- connect
    def connect(self):
        self.ser = serial.Serial(self.port_name, self.baud, timeout=0.2)
        time.sleep(2.0)  # let the MCU reset (ESP32/AVR reset-on-open)
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\n\r\n")
        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.connected = True
        self._stop_flag.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def disconnect(self):
        self._stop_flag.set()
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.connected = False
        self.state = "Disconnected"

    # ------------------------------------------------------------ reader loop
    def _reader_loop(self):
        buf = b""
        while not self._stop_flag.is_set():
            try:
                chunk = self.ser.read(256)
            except (serial.SerialException, OSError) as e:
                self.on_error(f"Serial read failed: {e}")
                self.connected = False
                return
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line.decode(errors="ignore").strip())

    def _handle_line(self, line):
        if not line:
            return
        if line.startswith("<") and line.endswith(">"):
            self._parse_status(line)
        elif line == "ok":
            self._ok_event.set()
        elif line.startswith("error:"):
            self._last_error = line
            self._ok_event.set()  # unblock the sender; job loop checks _last_error
            self.on_error(line)
        elif line.startswith("ALARM:"):
            self.state = "Alarm"
            self.on_alarm(line)
        elif line.startswith("Grbl "):
            pass  # startup banner
        # else: setting reports ($$) / feedback ([...]) - ignored for now

    def _parse_status(self, line):
        m = STATUS_RE.match(line)
        if not m:
            return
        self.state = m.group("state")
        if m.group("mpos"):
            self.mpos = tuple(float(v) for v in m.group("mpos").split(","))
        status = {
            "state": self.state,
            "mpos": self.mpos,
        }
        self.on_status(status)

    # ---------------------------------------------------------------- polling
    def request_status(self):
        """Send the GRBL real-time status query. Call this periodically
        (e.g. from a GLib.timeout_add in the UI) - it does not queue behind
        the job stream since '?' is a real-time command."""
        if self.connected and self.ser and self.ser.is_open:
            try:
                self.ser.write(b"?")
            except (serial.SerialException, OSError):
                pass

    # --------------------------------------------------------- simple sends
    def send_line(self, line, wait_ok=True, timeout=5.0):
        """Send a single gcode/command line and optionally block for 'ok'."""
        if not self.connected:
            raise RuntimeError("Not connected to GRBL")
        self._ok_event.clear()
        self._last_error = None
        with self._lock:
            self.ser.write((line.strip() + "\n").encode())
        if wait_ok:
            got = self._ok_event.wait(timeout)
            if not got:
                raise TimeoutError(f"No response for: {line}")
            if self._last_error:
                raise RuntimeError(self._last_error)

    def jog(self, axis, distance_mm, feed=1500):
        self.send_line(f"$J=G91 G21 {axis}{distance_mm} F{feed}")

    def home(self):
        self.send_line("$H", timeout=60)

    def unlock(self):
        self.send_line("$X")

    def soft_reset(self):
        if self.connected:
            self.ser.write(b"\x18")  # Ctrl-X

    def feed_hold(self):
        if self.connected:
            self.ser.write(b"!")

    def cycle_resume(self):
        if self.connected:
            self.ser.write(b"~")

    # -------------------------------------------------------------- job run
    def run_job(self, gcode_lines, on_progress=None, on_done=None):
        """Streams a full gcode program. Runs in its own worker thread so the
        UI stays responsive. on_progress(index, total, line) and
        on_done(success, message) fire from that thread - marshal to GTK
        with GLib.idle_add in the caller."""
        if self.job_running:
            raise RuntimeError("A job is already running")
        self._job_abort.clear()
        self._job_paused.clear()
        self.job_running = True

        def worker():
            total = len(gcode_lines)
            try:
                for i, raw in enumerate(gcode_lines):
                    line = raw.split(";", 1)[0].strip()  # strip comments
                    if not line:
                        continue
                    while self._job_paused.is_set():
                        time.sleep(0.1)
                        if self._job_abort.is_set():
                            break
                    if self._job_abort.is_set():
                        if on_done:
                            on_done(False, "Job aborted")
                        return
                    self.send_line(line, wait_ok=True, timeout=30)
                    self.on_line_sent(i, total, line)
                    if on_progress:
                        on_progress(i + 1, total, line)
                if on_done:
                    on_done(True, "Job complete")
            except Exception as e:  # noqa: BLE001 - surface any streaming failure
                if on_done:
                    on_done(False, str(e))
            finally:
                self.job_running = False

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def pause_job(self):
        self._job_paused.set()
        self.feed_hold()

    def resume_job(self):
        self._job_paused.clear()
        self.cycle_resume()

    def abort_job(self):
        self._job_abort.set()
        self._job_paused.clear()
        self.soft_reset()
