# Label Cutter Screen

A KlipperScreen-style touchscreen UI for a Raspberry Pi 4 driving a GRBL-based
label cutter/plotter with auto-feed, camera registration-mark detection, and
tilt correction applied before every cut.

## Architecture

- **UI**: GTK3 / PyGObject, same toolkit KlipperScreen uses. One
  `Gtk.ApplicationWindow` with a `Gtk.Stack` of panels (Home, Files, Job,
  Registration, Settings), bottom nav bar, same "panel exposes `build()`"
  pattern as KlipperScreen's `ScreenPanel` subclasses.
- **Machine link**: `grbl_controller.py` talks to GRBL 1.1 over **USB serial**.
  A dedicated reader thread parses `<...>` status reports and `ok`/`error`/
  `ALARM` responses; all callbacks are marshalled onto the GTK main loop with
  `GLib.idle_add` so the UI never blocks or gets touched from a worker thread.
- **Registration & tilt correction**: `registration.py` + `gcode_transform.py`.
  Every job goes: capture frame → locate the 4 registration marks near their
  expected positions → fit an affine (rotation + translation + minor scale)
  from nominal → detected mm positions → apply that affine to every X/Y (and
  arc I/J) in the G-code → **then** stream to GRBL. There is no "skip
  registration" path in `JobPanel.start_job()` on purpose.
- **Upload**: `upload_server.py` runs a small Flask server (default port
  8080) so you can push `.gcode`/`.nc` files from WiFi or Ethernet from any
  browser/phone/PC. The Files panel polls the same folder every 3s, so
  uploads show up automatically. Cutting itself always streams over the USB
  serial link to GRBL — upload path and cut path are independent.

## Install (Raspberry Pi OS / Debian)

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                  python3-opencv libatlas-base-dev
pip install -r requirements.txt --break-system-packages
```

## Configure

Edit `config.json` (copied to `~/.labelcutter_screen` conventions can be added
later; for now it lives next to `main.py`):

- `grbl.port` — your GRBL USB serial device (check with `ls /dev/ttyUSB*` or
  `/dev/ttyACM*`)
- `registration.nominal_machine_points_mm` — the 4 design-space (machine mm)
  coordinates where your registration marks are placed, matching your
  artwork/G-code
- `registration.px_per_mm` and `camera_origin_offset_mm` — one-time camera
  calibration values (see Registration panel's "Test Detection" button to
  dial these in)
- `network.gcode_dir` — where uploaded and local G-code files live

## Run

```bash
python3 main.py                # fullscreen, per config.json
python3 main.py --windowed     # for testing on a desktop, non-fullscreen
```

## Auto-start on boot

```bash
sudo cp systemd/labelcutter-screen.service /etc/systemd/system/
sudo systemctl enable --now labelcutter-screen.service
```

## Known limitation (documented, not hidden)

`gcode_transform.py` rotates/scales arc `I`/`J` offsets the same way as
endpoints, which is exact for pure rotation + uniform scale. If a fitted
correction has significant shear (unusual for a simple paper-skew fix),
arc shape will be slightly off. Straight-line-dominated label cut paths
(the common case) are unaffected.

## Next steps worth doing before production use

1. Swap Flask's dev server for `waitress` behind systemd for a cleaner
   shutdown story.
2. Add a proper camera calibration wizard (checkerboard-based) to replace
   the simple `px_per_mm` + offset model in `config.json`.
3. Add G-code preview (path drawing) to the Job panel before cutting starts.
4. If GRBL streaming throughput becomes a bottleneck at high feedrates,
   switch `grbl_controller.run_job` from line-by-line ok-wait to
   character-counting streaming (keep GRBL's 127-byte RX buffer full).
