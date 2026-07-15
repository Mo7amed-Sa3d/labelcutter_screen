import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


class FilesPanel:
    title = "Files"

    def __init__(self, window):
        self.win = window
        self.gcode_dir = window.upload_server.gcode_dir
        self.selected_file = None

    def build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        header = Gtk.Box(spacing=10)
        title = Gtk.Label(label="GCode Files")
        title.get_style_context().add_class("title")
        header.pack_start(title, False, False, 0)

        ip_hint = Gtk.Label(
            label=f"Upload at http://<this-pi-ip>:{self.win.upload_server.port}/"
        )
        ip_hint.get_style_context().add_class("status")
        header.pack_start(ip_hint, True, True, 0)
        box.pack_start(header, False, False, 0)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda _b: self._refresh())
        box.pack_start(refresh_btn, False, False, 0)

        self.list_store = Gtk.ListStore(str)
        self.tree_view = Gtk.TreeView(model=self.list_store)
        col = Gtk.TreeViewColumn("File", Gtk.CellRendererText(), text=0)
        self.tree_view.append_column(col)
        self.tree_view.get_selection().connect("changed", self._on_select)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.add(self.tree_view)
        box.pack_start(scroller, True, True, 0)

        self.selected_label = Gtk.Label(label="No file selected")
        self.selected_label.get_style_context().add_class("status")
        box.pack_start(self.selected_label, False, False, 0)

        start_btn = Gtk.Button(label="Start Job (register + cut)")
        start_btn.get_style_context().add_class("success")
        start_btn.connect("clicked", self._on_start_job)
        box.pack_start(start_btn, False, False, 0)

        self._refresh()
        # poll every 3s to pick up network uploads without a manual refresh
        GLib.timeout_add(3000, self._poll_refresh)
        return box

    def on_show(self):
        self._refresh()

    def _poll_refresh(self):
        self._refresh()
        return True

    def _refresh(self):
        current = set(self.list_store[i][0] for i in range(len(self.list_store)))
        try:
            files = set(sorted(os.listdir(self.gcode_dir)))
        except FileNotFoundError:
            files = set()
        if files != current:
            self.list_store.clear()
            for f in sorted(files):
                self.list_store.append([f])

    def _on_select(self, selection):
        model, it = selection.get_selected()
        if it is not None:
            self.selected_file = model[it][0]
            self.selected_label.set_text(f"Selected: {self.selected_file}")

    def _on_start_job(self, _btn):
        if not self.selected_file:
            self.win.panels["home"]._show_error("Select a gcode file first")
            return
        full_path = os.path.join(self.gcode_dir, self.selected_file)
        self.win.show_panel("job")
        self.win.panels["job"].start_job(full_path)
