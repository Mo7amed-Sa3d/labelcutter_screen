import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class HomePanel:
    title = "Home"

    def __init__(self, window):
        self.win = window
        self.grbl = window.grbl

    def build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label(label="Label Cutter")
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)

        status_row = Gtk.Box(spacing=10)
        self.state_label = Gtk.Label(label="State: Disconnected")
        self.state_label.get_style_context().add_class("status")
        self.pos_label = Gtk.Label(label="X:0.00 Y:0.00 Z:0.00")
        self.pos_label.get_style_context().add_class("value")
        status_row.pack_start(self.state_label, False, False, 0)
        status_row.pack_start(self.pos_label, False, False, 0)
        box.pack_start(status_row, False, False, 0)

        conn_row = Gtk.Box(spacing=10)
        connect_btn = Gtk.Button(label="Connect")
        connect_btn.connect("clicked", self._on_connect)
        disconnect_btn = Gtk.Button(label="Disconnect")
        disconnect_btn.connect("clicked", self._on_disconnect)
        unlock_btn = Gtk.Button(label="Unlock ($X)")
        unlock_btn.connect("clicked", lambda _b: self._safe(self.grbl.unlock))
        home_btn = Gtk.Button(label="Home ($H)")
        home_btn.connect("clicked", lambda _b: self._safe(self.grbl.home))
        for b in (connect_btn, disconnect_btn, unlock_btn, home_btn):
            conn_row.pack_start(b, True, True, 0)
        box.pack_start(conn_row, False, False, 0)

        # ------------------------------------------------------------ jog
        jog_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        step_mm = 10

        def jog_button(label, axis, distance):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b: self._safe(
                lambda: self.grbl.jog(axis, distance)))
            return b

        jog_grid.attach(jog_button("Y+", "Y", step_mm), 1, 0, 1, 1)
        jog_grid.attach(jog_button("X-", "X", -step_mm), 0, 1, 1, 1)
        jog_grid.attach(jog_button("X+", "X", step_mm), 2, 1, 1, 1)
        jog_grid.attach(jog_button("Y-", "Y", -step_mm), 1, 2, 1, 1)
        jog_grid.attach(jog_button("Z+", "Z", step_mm), 3, 0, 1, 1)
        jog_grid.attach(jog_button("Z-", "Z", -step_mm), 3, 2, 1, 1)
        box.pack_start(jog_grid, False, False, 0)

        return box

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self._show_error(str(e))

    def _show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.win, flags=0, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text="Error",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _on_connect(self, _btn):
        try:
            self.grbl.connect()
        except Exception as e:  # noqa: BLE001
            self._show_error(f"Could not connect: {e}")

    def _on_disconnect(self, _btn):
        self.grbl.disconnect()
        self.state_label.set_text("State: Disconnected")

    def on_status_update(self, status):
        self.state_label.set_text(f"State: {status['state']}")
        x, y, z = status["mpos"]
        self.pos_label.set_text(f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f}")
