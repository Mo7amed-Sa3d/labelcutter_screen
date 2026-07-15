import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class SettingsPanel:
    title = "Settings"

    def __init__(self, window):
        self.win = window
        self.config = window.config

    def build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label(label="Settings")
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        box.pack_start(grid, False, False, 0)

        row = 0
        self.port_entry = self._add_row(grid, row, "GRBL Serial Port",
                                         self.config.get("grbl", "port", default="/dev/ttyUSB0"))
        row += 1
        self.baud_entry = self._add_row(grid, row, "Baud Rate",
                                         str(self.config.get("grbl", "baud", default=115200)))
        row += 1
        self.cam_entry = self._add_row(grid, row, "Camera Index",
                                        str(self.config.get("camera", "index", default=0)))
        row += 1
        self.pxmm_entry = self._add_row(grid, row, "Pixels per mm",
                                         str(self.config.get("registration", "px_per_mm", default=10.0)))
        row += 1
        self.port_upload_entry = self._add_row(grid, row, "Upload Port",
                                                str(self.config.get("network", "upload_port", default=8080)))

        save_btn = Gtk.Button(label="Save (restart required)")
        save_btn.get_style_context().add_class("success")
        save_btn.connect("clicked", self._on_save)
        box.pack_start(save_btn, False, False, 0)

        note = Gtk.Label(
            label="Serial port / camera / network changes take effect after restarting the app."
        )
        note.get_style_context().add_class("status")
        box.pack_start(note, False, False, 0)

        return box

    def _add_row(self, grid, row, label_text, value):
        label = Gtk.Label(label=label_text, xalign=0)
        entry = Gtk.Entry()
        entry.set_text(value)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(entry, 1, row, 1, 1)
        return entry

    def _on_save(self, _btn):
        self.config.set(self.port_entry.get_text(), "grbl", "port")
        self.config.set(int(self.baud_entry.get_text()), "grbl", "baud")
        self.config.set(int(self.cam_entry.get_text()), "camera", "index")
        self.config.set(float(self.pxmm_entry.get_text()), "registration", "px_per_mm")
        self.config.set(int(self.port_upload_entry.get_text()), "network", "upload_port")
        self.config.save()
