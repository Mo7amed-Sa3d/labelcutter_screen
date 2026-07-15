"""
main_window.py
----------------
Mirrors KlipperScreen's core UI pattern: a single Gtk.ApplicationWindow with
a Gtk.Stack holding one page per "panel" (Home, Files, Job, Registration,
Settings), plus a persistent bottom nav bar of buttons that switch stack
pages. Panels are plain classes exposing build() -> Gtk.Widget so each one
is self-contained and easy to extend, same as KlipperScreen's ScreenPanel
subclasses.

All cross-panel shared state (grbl controller, registration system, config,
upload server) lives on this window and is handed to each panel at
construction time, so panels never reach into each other directly.
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

from grbl_controller import GrblController
from registration import RegistrationSystem
from upload_server import UploadServer

from ui.panels.home_panel import HomePanel
from ui.panels.files_panel import FilesPanel
from ui.panels.job_panel import JobPanel
from ui.panels.registration_panel import RegistrationPanel
from ui.panels.settings_panel import SettingsPanel


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title="Label Cutter")
        self.config = config

        w = config.get("screen", "width", default=1024)
        h = config.get("screen", "height", default=600)
        self.set_default_size(w, h)
        if config.get("screen", "fullscreen", default=False):
            self.fullscreen()

        self._load_css()

        # ---- shared backend objects, built once, handed to every panel ----
        self.grbl = GrblController(
            port=config.get("grbl", "port", default="/dev/ttyUSB0"),
            baud=config.get("grbl", "baud", default=115200),
            on_status=self._on_grbl_status,
            on_error=self._on_grbl_error,
            on_alarm=self._on_grbl_alarm,
        )
        self.registration = RegistrationSystem(
            camera_index=config.get("camera", "index", default=0),
            frame_size=(config.get("camera", "frame_width", default=1280),
                        config.get("camera", "frame_height", default=720)),
            px_per_mm=config.get("registration", "px_per_mm", default=10.0),
            origin_offset_mm=tuple(config.get("registration", "camera_origin_offset_mm",
                                               default=[0.0, 0.0])),
        )
        self.upload_server = UploadServer(
            gcode_dir=config.get("network", "gcode_dir", default="~/gcode_files"),
            port=config.get("network", "upload_port", default=8080),
        )
        self.upload_server.start()

        # last-known GRBL status, updated from the reader thread via
        # GLib.idle_add - panels read this instead of hitting serial directly
        self.status = {"state": "Disconnected", "mpos": (0.0, 0.0, 0.0)}

        # ---------------------------------------------------------- layout
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        root.pack_start(self.stack, True, True, 0)

        self.panels = {
            "home": HomePanel(self),
            "files": FilesPanel(self),
            "job": JobPanel(self),
            "registration": RegistrationPanel(self),
            "settings": SettingsPanel(self),
        }
        for name, panel in self.panels.items():
            self.stack.add_titled(panel.build(), name, panel.title)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        nav.set_margin_top(4)
        nav.set_margin_bottom(4)
        nav.set_margin_start(4)
        nav.set_margin_end(4)
        for name, panel in self.panels.items():
            btn = Gtk.Button(label=panel.title)
            btn.get_style_context().add_class("nav-button")
            btn.connect("clicked", lambda _b, n=name: self.show_panel(n))
            nav.pack_start(btn, True, True, 0)
        root.pack_end(nav, False, False, 0)

        # status polling - real-time '?' query on a timer, response arrives
        # asynchronously via on_status callback above
        poll_ms = config.get("grbl", "status_poll_interval_ms", default=250)
        GLib.timeout_add(poll_ms, self._poll_status)

        self.connect("destroy", self._on_destroy)

    def _load_css(self):
        css = Gtk.CssProvider()
        css.load_from_path(__file__.replace("main_window.py", "style.css"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def show_panel(self, name):
        self.stack.set_visible_child_name(name)
        if hasattr(self.panels[name], "on_show"):
            self.panels[name].on_show()

    # ------------------------------------------------------- GRBL callbacks
    # These fire from the serial reader thread - never touch GTK widgets
    # here directly, always marshal through GLib.idle_add.
    def _on_grbl_status(self, status):
        GLib.idle_add(self._apply_status, status)

    def _apply_status(self, status):
        self.status = status
        if "home" in self.panels:
            self.panels["home"].on_status_update(status)
        if "job" in self.panels:
            self.panels["job"].on_status_update(status)
        return False

    def _on_grbl_error(self, message):
        GLib.idle_add(self._show_error_dialog, "GRBL Error", message)

    def _on_grbl_alarm(self, message):
        GLib.idle_add(self._show_error_dialog, "GRBL Alarm", message)

    def _show_error_dialog(self, title, message):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
        return False

    def _poll_status(self):
        if self.grbl.connected:
            self.grbl.request_status()
        return True  # keep the GLib timeout running

    def _on_destroy(self, *_args):
        try:
            self.grbl.disconnect()
        except Exception:
            pass
        try:
            self.registration.close()
        except Exception:
            pass
