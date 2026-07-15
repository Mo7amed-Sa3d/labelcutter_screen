import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from gcode_transform import load_gcode, apply_affine_to_gcode, identity_affine
from registration import RegistrationError


class JobPanel:
    title = "Job"

    def __init__(self, window):
        self.win = window
        self.grbl = window.grbl
        self.registration = window.registration
        self.config = window.config

    def build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label(label="Job")
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)

        self.step_label = Gtk.Label(label="Idle")
        self.step_label.get_style_context().add_class("status")
        box.pack_start(self.step_label, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        box.pack_start(self.progress, False, False, 0)

        self.pos_label = Gtk.Label(label="")
        self.pos_label.get_style_context().add_class("value")
        box.pack_start(self.pos_label, False, False, 0)

        controls = Gtk.Box(spacing=10)
        pause_btn = Gtk.Button(label="Pause")
        pause_btn.connect("clicked", lambda _b: self.grbl.pause_job())
        resume_btn = Gtk.Button(label="Resume")
        resume_btn.connect("clicked", lambda _b: self.grbl.resume_job())
        stop_btn = Gtk.Button(label="Stop")
        stop_btn.get_style_context().add_class("danger")
        stop_btn.connect("clicked", lambda _b: self.grbl.abort_job())
        for b in (pause_btn, resume_btn, stop_btn):
            controls.pack_start(b, True, True, 0)
        box.pack_start(controls, False, False, 0)

        return box

    def on_status_update(self, status):
        x, y, z = status["mpos"]
        self.pos_label.set_text(f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f}")

    # ------------------------------------------------------------ job flow
    def start_job(self, gcode_path):
        """Full sequence: 1) detect registration marks, 2) fit tilt/offset
        correction, 3) apply it to the gcode, 4) stream to GRBL. Every job
        goes through registration first - this is the whole point of the
        machine, so there's no 'skip registration' shortcut in the flow."""
        if not self.grbl.connected:
            self._show_error("Connect to the machine first (Home panel)")
            return

        self.step_label.set_text("Detecting registration marks...")
        self.progress.set_fraction(0.0)

        try:
            self.registration.open()
            nominal_pts = self.config.get(
                "registration", "nominal_machine_points_mm", default=[]
            )
            search_radius = self.config.get(
                "registration", "mark_search_radius_px", default=60
            )
            pairs = self.registration.detect_marks(nominal_pts, search_radius)
            affine = self.registration.compute_affine(pairs)
            info = self.registration.describe_transform(affine)
            self.step_label.set_text(
                f"Tilt corrected: {info['tilt_deg']:.2f} deg, "
                f"offset ({info['offset_mm'][0]:.2f}, {info['offset_mm'][1]:.2f}) mm"
            )
        except RegistrationError as e:
            self._show_error(f"Registration failed: {e}")
            self.step_label.set_text("Idle")
            return
        finally:
            self.registration.close()

        lines = load_gcode(gcode_path)
        corrected = apply_affine_to_gcode(lines, affine)

        def on_progress(i, total, line):
            GLib.idle_add(self._update_progress, i, total, line)

        def on_done(success, message):
            GLib.idle_add(self._job_finished, success, message)

        self.grbl.run_job(corrected, on_progress=on_progress, on_done=on_done)

    def _update_progress(self, i, total, line):
        self.progress.set_fraction(i / total if total else 0)
        self.progress.set_text(f"{i}/{total}")
        return False

    def _job_finished(self, success, message):
        self.step_label.set_text(message)
        if success:
            self.progress.set_fraction(1.0)
        return False

    def _show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.win, flags=0, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text="Job Error",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
