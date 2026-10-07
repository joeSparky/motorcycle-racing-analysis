#!/usr/bin/env python3
"""
videoCalibration.py

Interactive two-point calibration between:
  * the helmet video ($video)
  * the AiM race CSV ($race)

Steve independently seeks MPV to a recognizable physical event and moves the
dot through the GPS samples until both show the same event. CALIBRATE START
records the first pair. CALIBRATE END records the second pair and writes:

    ${race without extension}.calibration

Standard environment variables:
    $race   current race CSV
    $video  current video file

MPV IPC socket:
    /tmp/mpvsocket
"""

import argparse
import csv
import json
import math
import os
import socket
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ImportError:
    raise SystemExit(
        "Matplotlib/Tk support is required.\n"
        "Install the Raspberry Pi packages for python3-matplotlib and python3-tk."
    )


SOCKET_PATH = r"\\.\pipe\race-analysis-calibration"


def load_race(path):
    """Read a raw AiM export through the local aimcsv.py cleaner."""
    aimcsv = Path(__file__).resolve().parent / "aimcsv.py"
    if not aimcsv.is_file():
        raise ValueError(f"aimcsv.py not found beside videoCalibration.py: {aimcsv}")

    try:
        result = subprocess.run(
            [sys.executable, str(aimcsv), str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        raise ValueError(f"aimcsv.py failed: {detail}")

    import io
    reader = csv.DictReader(io.StringIO(result.stdout))
    fields = reader.fieldnames or []

    needed = ["Time", "GPS Latitude", "GPS Longitude"]
    missing = [x for x in needed if x not in fields]
    if missing:
        raise ValueError("Missing CSV column(s): " + ", ".join(missing))

    rows = []
    for record_number, row in enumerate(reader, start=1):
        try:
            t = float(row["Time"])
            lat = float(row["GPS Latitude"])
            lon = float(row["GPS Longitude"])
        except (TypeError, ValueError):
            continue

        if not (math.isfinite(t) and math.isfinite(lat) and math.isfinite(lon)):
            continue
        if lat == 0.0 and lon == 0.0:
            continue

        rows.append({
            "record": record_number,
            "time": t,
            "lat": lat,
            "lon": lon,
        })

    if not rows:
        raise ValueError("No usable GPS samples were found in the race CSV.")
    return rows


from mpv_ipc import MpvConnection as Mpv, DEFAULT_PIPE


class CalibrationApp:
    def __init__(self, root, race_path, video_path, rows, mpv, mpv_process):
        self.root = root
        self.race_path = race_path
        self.video_path = video_path
        self.rows = rows
        self.mpv = mpv
        self.mpv_process = mpv_process
        self.index = 0
        self.start_pair = None
        self.end_pair = None

        root.title("Video Calibration")
        root.geometry("900x800")

        heading = tk.Label(
            root,
            text="VIDEO / GPS CALIBRATION",
            font=("TkDefaultFont", 18, "bold"),
        )
        heading.pack(pady=(10, 2))

        tk.Label(
            root,
            text="Match engine start/stop using audio and CSV time, or match a recognizable track event.",
        ).pack(pady=(0, 8))

        self.figure = Figure(figsize=(8.4, 3.4), dpi=100)
        self.ax = self.figure.add_subplot(111)

        lons = [r["lon"] for r in rows]
        lats = [r["lat"] for r in rows]

        self.ax.plot(lons, lats, linewidth=1)
        self.dot, = self.ax.plot(
            [rows[0]["lon"]], [rows[0]["lat"]],
            marker="o", markersize=3, linestyle="None"
        )
        self.ax.set_xlabel("GPS Longitude")
        self.ax.set_ylabel("GPS Latitude")
        self.ax.set_title("All GPS samples")
        self.ax.set_aspect("equal", adjustable="datalim")
        self.ax.grid(True, alpha=0.25)

        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10)

        info = tk.Frame(root)
        info.pack(pady=(5, 4))

        self.csv_label = tk.Label(
            info, text="", font=("TkFixedFont", 12, "bold")
        )
        self.csv_label.pack()

        self.video_label = tk.Label(
            info, text="MPV: connecting...", font=("TkFixedFont", 12)
        )
        self.video_label.pack()

        self.flip_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(
            info, text="Rotate video 180 degrees", variable=self.flip_enabled,
            command=self.rotate_video,
        ).pack()


        controls = tk.Frame(root)
        controls.pack(pady=6)

        for text, amount in [
            ("◀◀ 100", -100),
            ("◀ 10", -10),
            ("◀ 1", -1),
            ("1 ▶", 1),
            ("10 ▶", 10),
            ("100 ▶▶", 100),
        ]:
            tk.Button(
                controls,
                text=text,
                width=9,
                command=lambda n=amount: self.move(n),
            ).pack(side="left", padx=3)

        jump_controls = tk.Frame(root)
        jump_controls.pack(pady=(2, 5))

        tk.Button(
            jump_controls,
            text="GO TO START",
            width=16,
            command=self.go_to_start,
        ).pack(side="left", padx=5)

        tk.Button(
            jump_controls,
            text="GO TO END",
            width=16,
            command=self.go_to_end,
        ).pack(side="left", padx=5)

        time_controls = tk.Frame(root)
        time_controls.pack(pady=2)
        tk.Label(time_controls, text="CSV time (seconds):").pack(side="left")
        self.csv_entry = tk.Entry(time_controls, width=12)
        self.csv_entry.pack(side="left", padx=4)
        tk.Button(time_controls, text="Go", command=self.go_to_csv_time).pack(side="left")
        tk.Button(time_controls, text="Load saved start", command=lambda: self.load_point("start")).pack(side="left", padx=8)
        tk.Button(time_controls, text="Load saved end", command=lambda: self.load_point("end")).pack(side="left")

        calibrate = tk.Frame(root)
        calibrate.pack(pady=8)

        self.start_button = tk.Button(
            calibrate,
            text="SAVE START POINT",
            width=20,
            height=2,
            command=self.calibrate_start,
        )
        self.start_button.pack(side="left", padx=10)

        self.end_button = tk.Button(
            calibrate,
            text="SAVE END POINT",
            width=20,
            height=2,
            command=self.calibrate_end,
        )
        self.end_button.pack(side="left", padx=10)

        self.status = tk.Label(root, text="Start point has not been set.")
        self.status.pack(pady=(0, 4))
        tk.Button(root, text="Done", width=12, command=self.close).pack(pady=(0, 8))
        self.read_saved_points()

        # Keyboard GPS-dot movement. MPV keeps its own normal keyboard controls.
        root.bind("<Left>", lambda e: self.move(-1))
        root.bind("<Right>", lambda e: self.move(1))
        root.bind("<Shift-Left>", lambda e: self.move(-10))
        root.bind("<Shift-Right>", lambda e: self.move(10))
        root.bind("<Control-Left>", lambda e: self.move(-100))
        root.bind("<Control-Right>", lambda e: self.move(100))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_dot()
        self.poll_mpv()

    def read_saved_points(self):
        path = self.race_path.with_suffix(".calibration")
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if Path(data.get("video", "")) != self.video_path:
                if not messagebox.askyesno("Different video", "The saved calibration uses a different video. Load its points anyway?"):
                    return
            for key in ("pointA", "pointB"):
                pair = data[key]
                if not all(math.isfinite(float(pair[k])) for k in ("csvTime", "videoTime")):
                    raise ValueError("Invalid saved times")
            self.start_pair = data["pointA"]
            self.end_pair = data["pointB"]
            self.status.config(text="Saved start and end loaded. Load either point, adjust it, then save that point.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showwarning("Saved calibration", f"Could not load saved points: {exc}")

    def go_to_csv_time(self):
        try:
            target = float(self.csv_entry.get())
            if not math.isfinite(target):
                raise ValueError
        except ValueError:
            messagebox.showerror("CSV time", "Enter a time in seconds.")
            return
        self.index = min(range(len(self.rows)), key=lambda i: abs(self.rows[i]["time"] - target))
        self.refresh_dot()

    def load_point(self, which):
        pair = self.start_pair if which == "start" else self.end_pair
        if pair is None:
            messagebox.showinfo("No saved point", f"No {which} point has been set.")
            return
        try:
            self.mpv.command("set_property", "pause", True)
            self.mpv.command("seek", pair["videoTime"], "absolute+exact")
        except (OSError, ConnectionError) as exc:
            messagebox.showerror("Video", f"Could not seek to the saved point: {exc}")
            return
        self.index = min(range(len(self.rows)), key=lambda i: abs(self.rows[i]["time"] - pair["csvTime"]))
        self.csv_entry.delete(0, tk.END)
        self.csv_entry.insert(0, f"{pair['csvTime']:.3f}")
        self.refresh_dot()
        self.status.config(text=f"Loaded {which}: CSV {pair['csvTime']:.3f} / Video {pair['videoTime']:.3f}. Adjust, then save this point.")

    def rotate_video(self):
        try:
            filters = "hflip,vflip" if self.flip_enabled.get() else ""
            if not self.mpv.command("set_property", "vf", filters):
                raise ConnectionError("mpv could not rotate the video.")
        except (OSError, ConnectionError, json.JSONDecodeError) as e:
            self.mpv.close()
            messagebox.showerror("Video rotation", str(e))

    def current(self):
        return self.rows[self.index]

    def move(self, amount):
        self.index = max(0, min(len(self.rows) - 1, self.index + amount))
        self.refresh_dot()

    def go_to_start(self):
        self.index = 0
        self.refresh_dot()

    def go_to_end(self):
        self.index = len(self.rows) - 1
        self.refresh_dot()

    def refresh_dot(self):
        row = self.current()
        self.dot.set_data([row["lon"]], [row["lat"]])
        self.csv_label.config(
            text=(
                f"GPS sample {self.index + 1:,} / {len(self.rows):,}    "
                f"CSV Time {row['time']:.3f} s    Record {row['record']:,}"
            )
        )
        self.canvas.draw_idle()

    def video_time(self):
        try:
            value = self.mpv.get_property("time-pos")
            if value is None:
                raise ConnectionError
            return float(value)
        except (OSError, ConnectionError, json.JSONDecodeError):
            self.mpv.close()
            return None

    def poll_mpv(self):
        value = self.video_time()
        if value is None:
            self.video_label.config(text="MPV: waiting for connection...")
        else:
            self.video_label.config(text=f"MPV Video Time {value:.3f} s")
        self.root.after(100, self.poll_mpv)

    def capture_pair(self):
        video_time = self.video_time()
        if video_time is None:
            messagebox.showerror(
                "MPV not available",
                "Could not read the current MPV video time."
            )
            return None

        row = self.current()
        return {
            "record": row["record"],
            "csvTime": row["time"],
            "videoTime": video_time,
            "latitude": row["lat"],
            "longitude": row["lon"],
        }

    def calibrate_start(self):
        pair = self.capture_pair()
        if pair is None:
            return
        self.start_pair = pair
        if self.end_pair is not None:
            self.save_calibration()
            return
        self.status.config(
            text=(
                f"START set: CSV {pair['csvTime']:.3f} s  "
                f"↔ Video {pair['videoTime']:.3f} s"
            )
        )

    def calibrate_end(self):
        if self.start_pair is None:
            messagebox.showwarning(
                "Set start first",
                "Set CALIBRATE START before CALIBRATE END."
            )
            return

        pair = self.capture_pair()
        if pair is None:
            return

        if pair["csvTime"] == self.start_pair["csvTime"]:
            messagebox.showerror(
                "Invalid calibration",
                "Start and end CSV times cannot be identical."
            )
            return

        self.end_pair = pair
        self.save_calibration()

    def save_calibration(self):
        a = self.start_pair
        b = self.end_pair

        if b["csvTime"] <= a["csvTime"] or b["videoTime"] <= a["videoTime"]:
            messagebox.showerror("Invalid calibration", "End must be later than start in both CSV and video. The saved file was not changed.")
            return
        slope = (b["videoTime"] - a["videoTime"]) / (
            b["csvTime"] - a["csvTime"]
        )
        if not math.isfinite(slope) or slope <= 0:
            messagebox.showerror("Invalid calibration", "Choose a later point in both the video and GPS data for CALIBRATE END.")
            return
        offset = a["videoTime"] - slope * a["csvTime"]

        output = self.race_path.with_suffix(".calibration")
        data = {
            "race": str(self.race_path),
            "video": str(self.video_path),
            "slope": slope,
            "offset": offset,
            "pointA": a,
            "pointB": b,
        }

        with output.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.status.config(
            text=(
                f"CALIBRATION SAVED — slope {slope:.12f}, "
                f"offset {offset:.6f}"
            )
        )

        messagebox.showinfo(
            "Calibration saved",
            f"Saved:\n{output}\n\n"
            f"Start: CSV {a['csvTime']:.3f} ↔ Video {a['videoTime']:.3f}\n"
            f"End:   CSV {b['csvTime']:.3f} ↔ Video {b['videoTime']:.3f}"
        )

    def close(self):
        self.mpv.close()
        if self.mpv_process and self.mpv_process.poll() is None:
            self.mpv_process.terminate()
        self.root.destroy()


def launch_mpv(video_path, socket_path):
    try:
        Path(socket_path).unlink(missing_ok=True)
    except OSError:
        pass

    cmd = [
        os.environ.get("MPV_EXE", "mpv"),
        "--pause",
        "--keep-open=yes",
        "--no-config",
        "--no-fullscreen",
        "--geometry=640x360",
        f"--input-ipc-server={socket_path}",
        str(video_path),
    ]

    try:
        process = subprocess.Popen(cmd)
    except FileNotFoundError:
        raise SystemExit("mpv was not found on PATH.")

    for _ in range(50):
        probe = Mpv(socket_path)
        try:
            probe.connect()
            probe.close()
            return process
        except OSError:
            probe.close()
        if process.poll() is not None:
            raise SystemExit("mpv exited before its IPC socket was created.")
        time.sleep(0.1)

    process.terminate()
    raise SystemExit("Could not connect to mpv.")


def main():
    parser = argparse.ArgumentParser(
        description="Interactively calibrate helmet video to AiM GPS data."
    )
    parser.add_argument("--race", help="Override the $race CSV.")
    parser.add_argument("--video", help="Override the $video file.")
    parser.add_argument(
        "--socket", default=SOCKET_PATH,
        help=f"MPV IPC socket (default: {SOCKET_PATH})"
    )
    args = parser.parse_args()

    race_value = args.race or os.environ.get("race")
    video_value = args.video or os.environ.get("video")

    if not race_value:
        raise SystemExit("Race is not set. Use: source setRace FILE")
    if not video_value:
        raise SystemExit("Video is not set. Use: source setVideo VIDEOFILE")

    race_path = Path(race_value).expanduser().resolve()
    video_path = Path(video_value).expanduser().resolve()

    if not race_path.is_file():
        raise SystemExit(f"Race file not found: {race_path}")
    if not video_path.is_file():
        raise SystemExit(f"Video file not found: {video_path}")

    try:
        rows = load_race(race_path)
    except ValueError as e:
        raise SystemExit(str(e))

    process = launch_mpv(video_path, args.socket)
    mpv = Mpv(args.socket)

    root = tk.Tk()
    CalibrationApp(root, race_path, video_path, rows, mpv, process)
    root.mainloop()


if __name__ == "__main__":
    main()

