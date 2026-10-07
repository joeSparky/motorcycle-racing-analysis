#!/usr/bin/env python3
"""
theoreticalLap.py

Find the fastest traversal of every section in $track across one or more AiM
race/practice CSV files, then sum those winners into a theoretical best lap.

Defaults:
    track project: $track
    sessions:      $race

Examples:
    ./theoreticalLap.py
    ./theoreticalLap.py practice.csv race1.csv race2.csv
    ./theoreticalLap.py --track "$track" "$race"

Assumptions:
  * $track is the Track Editor JSON project and contains:
        "divisions": 10000
        "sections": [{"start": 0, "end": 943}, ...]
  * local aimcsv.py converts raw AiM CSV to ordinary CSV.
  * local track.py accepts clean CSV on stdin and emits CSV containing
    Time, TrackPosition and Lap (or LapNumber).
"""

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path


def die(msg):
    raise SystemExit("theoreticalLap.py: " + msg)


def find_tool(name):
    here = Path(__file__).resolve().parent
    p = here / name
    if p.exists():
        return str(p)
    return name


def run_pipeline(session, track_project):
    """raw AiM CSV -> aimcsv.py -> track.py -> list of dict rows"""
    aimcsv = find_tool("aimcsv.py")
    trackpy = find_tool("track.py")

    try:
        a = subprocess.run(
            [sys.executable, aimcsv, str(session)],
            text=True, capture_output=True, check=True
        )
    except subprocess.CalledProcessError as e:
        die(f"aimcsv.py failed for {session}:\n{e.stderr.strip()}")

    try:
        t = subprocess.run(
            [sys.executable, trackpy, "--track", str(track_project)],
            input=a.stdout, text=True, capture_output=True, check=True
        )
    except subprocess.CalledProcessError as e:
        die(f"track.py failed for {session}:\n{e.stderr.strip()}")

    rows = list(csv.DictReader(io.StringIO(t.stdout)))
    if not rows:
        die(f"track.py returned no CSV rows for {session}")
    return rows


def pick_field(fields, candidates):
    low = {f.lower(): f for f in fields}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    return None


def numeric_rows(rows):
    if not rows:
        return []
    fields = rows[0].keys()
    tf = pick_field(fields, ["Time", "Time (s)", "time"])
    pf = pick_field(fields, ["TrackPosition", "Position", "track_position"])
    lf = pick_field(fields, ["Lap", "LapNumber", "lap"])
    of = pick_field(fields, ["OffTrack", "off_track"])
    cf = pick_field(fields, ["Continuity", "continuity"])

    if not tf or not pf or not lf:
        die("track.py output must contain Time, TrackPosition and Lap columns.\n"
            "Columns received: " + ", ".join(fields))

    out = []
    for r in rows:
        try:
            t = float(r[tf])
            p = float(r[pf])
            lap = int(float(r[lf]))
        except (ValueError, TypeError):
            continue

        off = False
        if of:
            off = str(r.get(of, "")).strip().lower() in ("1","true","yes","y")

        continuity = r.get(cf, "") if cf else ""
        out.append({
            "time": t, "pos": p, "lap": lap,
            "off": off, "continuity": continuity
        })
    return out


def crossing_time(a, b, boundary, divisions):
    """
    Interpolate time at a boundary for two consecutive samples on the same lap.
    Positions are unwrapped locally so the 10000->0 seam behaves correctly.
    """
    p0, p1 = a["pos"], b["pos"]
    x = float(boundary)

    # unwrap large seam jumps
    if p1 - p0 < -divisions/2:
        p1 += divisions
    elif p1 - p0 > divisions/2:
        p0 += divisions

    # represent boundary in same local turn
    while x < min(p0, p1) - 1e-9:
        x += divisions
    while x > max(p0, p1) + 1e-9:
        x -= divisions

    lo, hi = sorted((p0, p1))
    if x < lo - 1e-9 or x > hi + 1e-9 or p1 == p0:
        return None

    f = (x - p0) / (p1 - p0)
    if f < -1e-9 or f > 1+1e-9:
        return None
    return a["time"] + f * (b["time"] - a["time"])


def lap_crossings(rows, boundaries, divisions):
    """
    Return {lap: {boundary: crossing_time}}.
    Only adjacent samples from the same lap are used.
    """
    result = {}
    for a, b in zip(rows, rows[1:]):
        if a["lap"] != b["lap"] or a["off"] or b["off"]:
            continue
        # Reject backwards time and conspicuously large data gaps.
        dt = b["time"] - a["time"]
        if dt <= 0 or dt > 2.0:
            continue

        for boundary in boundaries:
            ct = crossing_time(a, b, boundary, divisions)
            if ct is not None:
                result.setdefault(a["lap"], {})
                # A normal lap should cross once. Keep first crossing.
                result[a["lap"]].setdefault(boundary, ct)
    return result


def section_time(cross, start, end, divisions):
    """
    For ordinary sections use same-lap start/end crossings.
    For the final section ending at divisions, its end is boundary 0 of next lap.
    """
    if end == divisions:
        # start is in lap L; finish line is 0 at transition to next lap.
        return None
    if start not in cross or end not in cross:
        return None
    dt = cross[end] - cross[start]
    return dt if dt > 0 else None


def analyze_session(session, track_project, sections, divisions):
    rows = numeric_rows(run_pipeline(session, track_project))
    boundaries = sorted(set(
        [0] +
        [int(s["start"]) for s in sections] +
        [0 if int(s["end"]) == divisions else int(s["end"]) for s in sections]
    ))
    crossings = lap_crossings(rows, boundaries, divisions)

    results = []
    laps = sorted(crossings)

    # ordinary sections
    for sec in sections:
        start, end = int(sec["start"]), int(sec["end"])
        if end != divisions:
            for lap in laps:
                c = crossings[lap]
                dt = section_time(c, start, end, divisions)
                if dt is not None:
                    results.append({
                        "section": end, "start": start, "end": end,
                        "lap": lap, "start_time": c[start],
                        "end_time": c[end], "time": dt,
                        "source": str(session)
                    })
        else:
            # final section: start crossing on lap L -> finish-line (0) crossing
            # belonging to the next lap. Use chronological row interpolation
            # and pair each start with the next 0 crossing after it.
            starts = []
            finishes = []
            for a,b in zip(rows,rows[1:]):
                if a["off"] or b["off"] or b["time"] <= a["time"] or b["time"]-a["time"] > 2:
                    continue
                st = crossing_time(a,b,start,divisions)
                if st is not None:
                    starts.append((st,a["lap"]))
                ft = crossing_time(a,b,0,divisions)
                if ft is not None:
                    finishes.append(ft)
            # deduplicate near-identical crossing detections
            def uniq(vals, keyed=False):
                out=[]
                for v in sorted(vals, key=lambda x:x[0] if keyed else x):
                    x=v[0] if keyed else v
                    ox=(out[-1][0] if keyed else out[-1]) if out else None
                    if ox is None or abs(x-ox)>0.05: out.append(v)
                return out
            starts=uniq(starts,True); finishes=uniq(finishes)
            for st,lap in starts:
                ft=next((x for x in finishes if x>st+1e-6),None)
                if ft is not None and 0 < ft-st < 120:
                    results.append({
                        "section": divisions, "start": start, "end": divisions,
                        "lap": lap, "start_time": st, "end_time": ft,
                        "time": ft-st, "source": str(session)
                    })
    return results



def actual_laps_for_session(session, track_project, sections, divisions):
    """Return complete actual laps measured from position 0 to the next position 0."""
    rows = numeric_rows(run_pipeline(session, track_project))
    finishes = []
    for a, b in zip(rows, rows[1:]):
        if a["off"] or b["off"]:
            continue
        dt = b["time"] - a["time"]
        if dt <= 0 or dt > 2.0:
            continue
        ct = crossing_time(a, b, 0, divisions)
        if ct is not None:
            finishes.append(ct)

    # Crossing detection can see the same seam in adjacent pairs; deduplicate.
    clean = []
    for t in sorted(finishes):
        if not clean or abs(t - clean[-1]) > 0.05:
            clean.append(t)

    result = []
    for i in range(len(clean)-1):
        dt = clean[i+1] - clean[i]
        if 10.0 < dt < 600.0:
            # Find the track.py observed lap number just after the first crossing.
            lap = None
            for r in rows:
                if r["time"] >= clean[i]:
                    lap = r["lap"]
                    break
            result.append({
                "lap": lap,
                "start_time": clean[i],
                "end_time": clean[i+1],
                "time": dt,
                "source": str(session)
            })
    return result


def fmt(x):
    return f"{x:.3f}"


def main():
    ap = argparse.ArgumentParser(
        description="Build a theoretical best lap from fastest section times."
    )
    ap.add_argument("sessions", nargs="*", help="AiM race/practice CSV files")
    ap.add_argument("--track", default=os.environ.get("track"),
                    help="Track Editor JSON project (default: $track)")
    ap.add_argument("--json", dest="json_out",
                    help="also write detailed results to this JSON file")
    args = ap.parse_args()

    if not args.track:
        die("set $track or use --track FILE")

    sessions = args.sessions or ([os.environ["race"]] if os.environ.get("race") else [])
    if not sessions:
        die("set $race or supply one or more session CSV files")

    track_project = Path(args.track)
    data = json.loads(track_project.read_text(encoding="utf-8"))
    divisions = int(data.get("divisions", 10000))
    sections = data.get("sections") or []
    if not sections:
        die(f"{track_project} contains no sections")

    sections = sorted(
        [{"start": int(s["start"]), "end": int(s["end"])} for s in sections],
        key=lambda s: s["start"]
    )

    all_results = []
    for session in sessions:
        all_results.extend(
            analyze_session(Path(session), track_project, sections, divisions)
        )

    if not all_results:
        die("no complete section traversals were found")

    all_actual_laps = []
    for session in sessions:
        all_actual_laps.extend(
            actual_laps_for_session(Path(session), track_project, sections, divisions)
        )

    winners = []
    print()
    print(f'THEORETICAL BEST LAP — {data.get("track", track_project.stem)}')
    print()
    print(f'{"Section":>8}  {"Time":>9}  {"Lap":>5}  Source')
    print("-" * 68)

    for sec in sections:
        sid = sec["end"]
        candidates = [r for r in all_results if r["section"] == sid]
        if not candidates:
            print(f"{sid:>8}  {'---':>9}  {'---':>5}  no complete pass")
            continue
        best = min(candidates, key=lambda r: r["time"])
        winners.append(best)
        print(f'{sid:>8}  {fmt(best["time"]):>9}  {best["lap"]:>5}  {Path(best["source"]).name}')

    print("-" * 68)
    if len(winners) == len(sections):
        total = sum(r["time"] for r in winners)
        print(f'{"THEORETICAL":>12}  {fmt(total):>9}')
    else:
        total = None
        print("THEORETICAL LAP unavailable: one or more sections have no complete pass.")

    best_actual = min(all_actual_laps, key=lambda r: r["time"]) if all_actual_laps else None
    if best_actual:
        print(f'{"BEST ACTUAL":>12}  {fmt(best_actual["time"]):>9}  '
              f'L{best_actual["lap"]}  {Path(best_actual["source"]).name}')
        if total is not None:
            potential = best_actual["time"] - total
            print(f'{"POTENTIAL":>12}  {fmt(potential):>9}')
    else:
        potential = None
        print(f'{"BEST ACTUAL":>12}  {"---":>9}  no complete lap found')

    if args.json_out:
        payload = {
            "track": data.get("track"),
            "divisions": divisions,
            "sessions": [str(Path(x)) for x in sessions],
            "theoretical_time": total,
            "best_actual_lap": best_actual,
            "potential_improvement": potential,
            "winners": winners,
            "all_section_passes": all_results,
            "all_actual_laps": all_actual_laps,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nDetailed results: {args.json_out}")


if __name__ == "__main__":
    main()
