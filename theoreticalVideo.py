#!/usr/bin/env python3
"""
theoreticalVideo.py

Play the current theoretical-best lap by jumping among winning sections
in the calibrated helmet video.

Uses:
    $race   current raw AiM CSV
    $track  Track Editor JSON
    $video  current helmet video

Requires, in the same racingTools directory:
    theoreticalLap.py
    mpv

Calibration file:
    ${race_without_extension}.calibration

The calibration is expected to contain slope and offset such that:
    video_time = slope * csv_time + offset
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def die(msg):
    raise SystemExit("theoreticalVideo.py: " + msg)


def tool(name):
    p = Path(__file__).resolve().parent / name
    return str(p) if p.exists() else name


def load_calibration(race):
    p = Path(race).with_suffix(".calibration")
    if not p.exists():
        die(f"calibration file not found: {p}")

    text = p.read_text(encoding="utf-8")
    # Accept JSON if calibration was saved that way.
    try:
        d = json.loads(text)
        return float(d["slope"]), float(d["offset"]), p
    except Exception:
        pass

    vals = {}
    for line in text.splitlines():
        m = re.match(r"\s*(slope|offset)\s*[:=]\s*([-+0-9.eE]+)", line)
        if m:
            vals[m.group(1)] = float(m.group(2))
    if "slope" not in vals or "offset" not in vals:
        die(f"could not read slope/offset from {p}")
    return vals["slope"], vals["offset"], p


def theoretical_results(race, track):
    fd, name = tempfile.mkstemp(prefix="theoretical-", suffix=".json")
    os.close(fd)
    try:
        cmd = [
            sys.executable, tool("theoreticalLap.py"),
            "--track", str(track), "--json", name, str(race)
        ]
        r = subprocess.run(cmd, text=True, capture_output=True)
        if r.returncode:
            die("theoreticalLap.py failed:\n" + (r.stderr or r.stdout).strip())
        return json.loads(Path(name).read_text(encoding="utf-8"))
    finally:
        Path(name).unlink(missing_ok=True)


def merge_winners(winners):
    """
    Merge adjacent theoretical sections when they come from the same source/lap
    and their CSV times touch. This makes playback smoother.
    """
    pieces = []
    for w in winners:
        q = {
            "sections": [w["section"]],
            "lap": w["lap"],
            "source": w["source"],
            "start_time": float(w["start_time"]),
            "end_time": float(w["end_time"]),
            "section_time": float(w["time"]),
        }
        if pieces:
            p = pieces[-1]
            same = (p["source"] == q["source"] and p["lap"] == q["lap"])
            touching = abs(p["end_time"] - q["start_time"]) < 0.20
            if same and touching:
                p["sections"].extend(q["sections"])
                p["end_time"] = q["end_time"]
                p["section_time"] += q["section_time"]
                continue
        pieces.append(q)
    return pieces


class MPV:
    def __init__(self, video, socket_path, audio=False, flip=False):
        self.socket_path = socket_path
        Path(socket_path).unlink(missing_ok=True)
        cmd = [
            "mpv", "--pause", "--no-fullscreen", "--geometry=960x540",
            f"--input-ipc-server={socket_path}",
        ]
        if not audio:
            cmd.append("--no-audio")
        if flip:
            cmd.append("--vf=hflip,vflip")
        cmd.append(str(video))
        self.proc = subprocess.Popen(cmd)
        deadline = time.time() + 8
        while time.time() < deadline:
            if Path(socket_path).exists():
                return
            if self.proc.poll() is not None:
                die("mpv exited before IPC socket became available")
            time.sleep(.05)
        die("timed out waiting for mpv")

    def command(self, *args):
        msg = json.dumps({"command": list(args)}) + "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(self.socket_path)
            s.sendall(msg.encode())
            data = b""
            while b"\n" not in data:
                data += s.recv(4096)
        return json.loads(data.split(b"\n",1)[0])

    def seek(self, seconds):
        self.command("seek", float(seconds), "absolute+exact")

    def pause(self, yes):
        self.command("set_property", "pause", bool(yes))

    def time_pos(self):
        try:
            r = self.command("get_property", "time-pos")
            return float(r.get("data"))
        except Exception:
            return None

    def close(self):
        try:
            self.command("quit")
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Play the theoretical best lap in MPV.")
    ap.add_argument("--race", default=os.environ.get("race"))
    ap.add_argument("--track", default=os.environ.get("track"))
    ap.add_argument("--video", default=os.environ.get("video"))
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--flip", action="store_true")
    ap.add_argument("--socket", default="/tmp/mpv-theoretical")
    args = ap.parse_args()

    if not args.race: die("set $race or use --race FILE")
    if not args.track: die("set $track or use --track FILE")
    if not args.video: die("set $video or use --video FILE")

    slope, offset, cal = load_calibration(args.race)
    result = theoretical_results(args.race, args.track)
    winners = result.get("winners") or []
    if not winners:
        die("theoreticalLap.py returned no winning sections")

    pieces = merge_winners(winners)

    def vt(csv_time):
        return slope * float(csv_time) + offset

    print(f'Theoretical lap: {result.get("theoretical_time", 0):.3f} s')
    print(f'Video: {args.video}')
    print(f'Calibration: {cal.name}')
    print()
    print("Playback pieces:")
    for i,p in enumerate(pieces,1):
        secs=",".join(str(x) for x in p["sections"])
        print(f'  {i:2d}. section(s) {secs:<15} lap {p["lap"]:<3} '
              f'{p["section_time"]:7.3f} s  video {vt(p["start_time"]):.3f}-{vt(p["end_time"]):.3f}')
    print()
    print("SPACE in the terminal pauses/resumes only if your terminal sends input;")
    print("normal MPV keyboard controls also remain available.")
    print("Press Ctrl-C to stop.")

    mpv = MPV(args.video, args.socket, args.audio, args.flip)
    try:
        # Small tolerance avoids switching late because of IPC polling.
        for i,p in enumerate(pieces,1):
            start_v = vt(p["start_time"])
            end_v = vt(p["end_time"])
            if end_v <= start_v:
                die(f"invalid calibrated video range for section {p['sections']}")

            secs=",".join(str(x) for x in p["sections"])
            print(f'Playing {secs}  lap {p["lap"]} ...', flush=True)
            mpv.pause(True)
            mpv.seek(start_v)
            time.sleep(.08)
            mpv.pause(False)

            while True:
                if mpv.proc.poll() is not None:
                    return
                pos = mpv.time_pos()
                if pos is not None and pos >= end_v - 0.015:
                    break
                time.sleep(.025)

        mpv.pause(True)
        print("Theoretical lap complete.")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        mpv.close()


if __name__ == "__main__":
    main()
