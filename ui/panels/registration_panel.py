import cv2
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GdkPixbuf

from registration import RegistrationError


class RegistrationPanel:
    title = "Registration"

    def __init__(self, window):
        self.win = window
        self.registration = window.registration
        self.config = window.config
        self._preview_active = False
        self._timeout_id = None

    def build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label(label="Registration & Tilt Correction")
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)

        self.image = Gtk.Image()
        frame = Gtk.Frame()
        frame.add(self.image)
        box.pack_start(frame, True, True, 0)

        self.result_label = Gtk.Label(label="Preview stopped")
        self.result_label.get_style_context().add_class("status")
        box.pack_start(self.result_label, False, False, 0)

        controls = Gtk.Box(spacing=10)
        preview_btn = Gtk.Button(label="Start Preview")
        preview_btn.connect("clicked", self._toggle_preview)
        self._preview_btn = preview_btn
        test_btn = Gtk.Button(label="Test Detection")
        test_btn.connect("clicked", self._run_test_detection)
        controls.pack_start(preview_btn, True, True, 0)
        controls.pack_start(test_btn, True, True, 0)
        box.pack_start(controls, False, False, 0)

        return box

    def on_show(self):
        pass

    def _toggle_preview(self, _btn):
        if self._preview_active:
            self._stop_preview()
        else:
            self._start_preview()

    def _start_preview(self):
        try:
            self.registration.open()
        except RegistrationError as e:
            self.result_label.set_text(f"Camera error: {e}")
            return
        self._preview_active = True
        self._preview_btn.set_label("Stop Preview")
        fps = self.config.get("camera", "preview_fps", default=8)
        interval_ms = max(1, int(1000 / fps))
        self._timeout_id = GLib.timeout_add(interval_ms, self._update_frame)

    def _stop_preview(self):
        self._preview_active = False
        self._preview_btn.set_label("Start Preview")
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None
        self.registration.close()
        self.result_label.set_text("Preview stopped")

    def _update_frame(self):
        if not self._preview_active:
            return False
        try:
            frame = self.registration.grab_frame()
        except RegistrationError:
            return True  # transient camera hiccup, keep polling
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            rgb.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3
        )
        # scale down to keep the widget light on the Pi's GPU
        scaled = pixbuf.scale_simple(640, int(640 * h / w), GdkPixbuf.InterpType.BILINEAR)
        self.image.set_from_pixbuf(scaled)
        return True

    def _run_test_detection(self, _btn):
        was_active = self._preview_active
        if not was_active:
            try:
                self.registration.open()
            except RegistrationError as e:
                self.result_label.set_text(f"Camera error: {e}")
                return
        try:
            nominal_pts = self.config.get(
                "registration", "nominal_machine_points_mm", default=[]
            )
            search_radius = self.config.get(
                "registration", "mark_search_radius_px", default=60
            )
            pairs = self.registration.detect_marks(nominal_pts, search_radius)
            affine = self.registration.compute_affine(pairs)
            info = self.registration.describe_transform(affine)
            self.result_label.set_text(
                f"OK - tilt {info['tilt_deg']:.2f} deg, "
                f"offset ({info['offset_mm'][0]:.2f}, {info['offset_mm'][1]:.2f}) mm"
            )
        except RegistrationError as e:
            self.result_label.set_text(f"Detection failed: {e}")
        finally:
            if not was_active:
                self.registration.close()
