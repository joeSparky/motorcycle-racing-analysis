# Motorcycle Racing Analysis

Windows tools for reviewing AiM race data alongside helmet-camera video. The launcher brings together video calibration, a configurable dashboard, statistics, track segments, and session information.

## Contents

- [Download and Install](#download-and-install)
- [Directories](#directories)
- [Export Track Information](#export-track-information)
- [Import Track Information](#import-track-information)
- [Track Segments](#track-segments)
- [File Types](#file-types)
- [Prepare a Recording](#prepare-a-recording)
- [Use the Analysis Tools](#use-the-analysis-tools)
- [Optional: export track coordinates to CSV](#optional-export-track-coordinates-to-csv)
- [Personal settings, backups, and updates](#personal-settings-backups-and-updates)
- [Troubleshooting](#troubleshooting)
- [Note: software folder location](#note-software-folder-location)

## Download and Install

You need:

- A Windows PC with a writable folder for the software and racing data.
- Internet access to download the tools and complete initial setup.

### Install and verify the software

1. Install **Python 3.9 or newer** from [python.org](https://www.python.org/downloads/windows/). Use 64-bit Python, include **Tcl/Tk support**, and select **Add Python to PATH** during installation. Tkinter is included with Python's Tcl/Tk support; it does not require a separate download. If a suitable Python installation is already present, you can use it.

   **Verify Python before continuing:** open a new PowerShell window after installation and run:

   ```powershell
   python --version
   ```

   You should see `Python 3.x.x`, with version 3.9 or newer (for example, `Python 3.13.12`). If the command is not recognized or opens the Microsoft Store, check that Python is installed with **Add Python to PATH** selected, then open a new PowerShell window and try again.

   **Verify Tkinter:** in the same PowerShell window, run:

   ```powershell
   python -m tkinter
   ```

   A small demonstration window should open and display the Tcl/Tk version. If it opens, Tkinter is installed and working. Close the demonstration window before continuing. If an error reports that Tkinter is missing, modify or reinstall Python with **Tcl/Tk support**, then repeat this check.

2. Install **AiM Race Studio 3**: open the [official Race Studio 3 download page](https://www.aimtechnologies.com/support/downloads/software-downloads/race-studio-3/), click **Download**, and follow the installation instructions. You will use Race Studio 3 to export track information and original race-data CSV files from your AiM recordings. If it is already installed, use your existing installation.

   **Verify before continuing:** open Race Studio 3 from the Windows Start menu and confirm that it starts successfully. Complete any registration prompts it presents.

3. **Download the Racing Analysis Software.** Choose either Step 3A or Step 3B; you do not need both.

   **3A. Download a ZIP**

   Open [the GitHub repository](https://github.com/joeSparky/motorcycle-racing-analysis), choose **Code > Download ZIP**, then extract the entire ZIP into a writable folder such as `Documents\Race Analysis`. Do not run the files inside the ZIP.

   **3B. Clone with Git**

   If Git is installed, open PowerShell in the parent folder where you want to keep the software and run:

   ```powershell
   git clone https://github.com/joeSparky/motorcycle-racing-analysis.git
   ```

   This creates a `motorcycle-racing-analysis` folder containing the software.

   **Verify before continuing:** open the extracted or cloned software folder in File Explorer and confirm that it contains `Setup.cmd`, `setup.ps1`, `Race-Analysis.cmd`, and `launcher.py`.

4. **Run Setup.cmd.** In the extracted or cloned software folder, double-click **Setup.cmd**. Keep its window open until it finishes.

   **Verify before continuing:** wait for **SETUP COMPLETE**. If setup stops, read the message and `setup-log.txt`, resolve the problem, and rerun `Setup.cmd` before continuing.

5. **Open the launcher.** Double-click **Race-Analysis.cmd** in the software folder.

   **Verify before continuing:** the **Steve's Race Analysis** launcher window should open with file selectors and buttons including **Calibrate Video**, **Open Dashboard**, **Statistics**, and **Edit Segments**.

## Directories

Keep your racing data outside the software folder so it is easier to back up and retain when updating the tools. For example:

```text
Documents\
  Race Analysis\             software and setup files
  racingData\
    Nelson Ledges\
      NelsonLedges.ztracks    track export from Race Studio 3
      NelsonLedges.json       track project created by the launcher
      practice.csv           original race-data CSV exported from AiM
      practice.mp4           helmet-camera video
      practice.calibration   created by video calibration
      reference-points.json  optional interesting points
```

1. In the launcher, use **Browse...** beside **racingData folder** to choose where to keep your racing data. This field starts blank on a fresh installation.
2. Use **New track folder...** to create a folder for your track, or **Browse...** beside **Track data folder** to select an existing one.

**Verify before continuing:** the launcher shows your chosen racingData folder and track data folder.

Folder selection does not copy or move your files. Selecting a track folder clears the four file selections, so select that track's race CSV, video, track project, and optional points afterward.

The launcher remembers your folder and file selections. Close all analysis windows before changing them.

## Export Track Information

1. Open **Race Studio 3**.

2. Hover over the icons until you find one labeled **Tracks**, then select that icon.

3. Enter the desired track in the search field.

4. Put a check mark in the box next to the desired track.

5. Click the **Export** button.

6. Select the track folder inside your **racingData** folder. Enter the track name as the file name, then click **Save**.

   **Verify before continuing:** confirm that the track folder contains the exported `.ztracks` file.

7. Close **Race Studio 3**.

## Import Track Information

1. Return to the launcher window opened earlier.

2. Click **Import .ztracks...** beside **Track project**. Select the `.ztracks` file recently exported from Race Studio 3.

3. Click **Open**.

4. Enter a track name and save the resulting **track-project JSON** in the same data folder. The launcher selects and remembers that JSON.

The importer preserves the original export and works offline. It closes the reference outline and scales distance around the track to positions **0–10000**. Position zero is the export's first point, and the source point order is assumed to be the riding direction. Inspect both before relying on segment results; importing does not automatically identify the official start/finish line.

The decoder supports the observed AiM binary track layout used during development. An unsupported export produces an error; support for every Race Studio export format is not established.

## Track Segments

1. Click **Edit Segments** in the launcher to inspect the track outline.
2. Click the track to add section boundaries. At least two sections are required to save.
3. Drag a boundary to move it, or right-click a boundary to remove it and merge adjacent sections.
4. Click **SAVE SECTIONS** to save into the track-project JSON. Closing the editor does not save unsaved edits.
5. Close the segment editor when finished.

## File Types

| File | Where it comes from | Use |
|---|---|---|
| Original race-data CSV | AiM recording exported through Race Studio | Recorded time, channels, GPS, and available session/lap metadata; select this in **Race CSV** |
| Track-project JSON | Launcher's **Import .ztracks...** | Reference track geometry and saved segments; select this in **Track project** |
| Interesting-points JSON | Saved from the dashboard track map or compatible points editor | Optional cornering and landmark references; select this in **Interesting points** |
| Track-coordinate CSV | Optional `trackcsv.py` conversion | Coordinate export for separate tools; not a substitute for the original race CSV and not required by the launcher import workflow |

No track YAML file is required for this launcher workflow. `dashboard.yaml` configures the dashboard gauges and appearance; it is not track geometry.

## Prepare a Recording

1. Export the recording from AiM as an original race-data CSV and save it in the track data folder. Preserve the export's metadata and channel/unit headers rather than resaving it through a spreadsheet editor.
2. In the launcher, choose that file under **Race CSV**.
3. Choose the corresponding **Helmet video**. For a camera recording split across files, use **Select Video Pieces...**, inspect the proposed order, and confirm only pieces from one continuous recording. This creates a saved video timeline rather than merging the video files.
4. Choose the prepared **Track project** for map and segment features. Leave **Interesting points** blank on the first run unless you already have a matching points file.
5. Click **Calibrate Video**. Match a recognizable early event or location in the video to its corresponding GPS/data sample, then click **CALIBRATE START**.
6. Match a second event later in both the video and recording, then click **CALIBRATE END**. Use well-separated matching points to establish the timing relationship.
7. The tool saves a `.calibration` file beside the race CSV. Close calibration, then click **Open Dashboard**.

The dashboard requires an existing calibration for the selected recording. The launcher checks calibration timing and warns when the selected video differs from the one stored in calibration. Calibrate again for a new recording/video pairing rather than assuming another recording's timing will work.

## Use the Analysis Tools

| Launcher button | What it does | Required inputs |
|---|---|---|
| **Calibrate Video** | Align recorded data with video time | Race CSV and helmet video; working mpv setup |
| **Open Dashboard** | Play video with gauges; access track map, lap, and segment analysis | Race CSV, video, saved calibration; track project for map/track-segment features |
| **Statistics** | Evaluate channel expressions over recording, time, lap, or segment intervals | Race CSV; track project for track-position segments |
| **Edit Segments** | Define and save track section boundaries | Track-project JSON |
| **Session Information** | Display metadata supplied by the AiM export | Race CSV |

Statistics and Session Information do not need video or calibration. Statistics and Dashboard can stay open together when started from the same launcher. Statistics can seek the running dashboard video by clicking its graph or using its navigation buttons. Close calibration before opening Dashboard.

In Dashboard, use **Edit gauges...** to add, remove, arrange, or configure gauges. **Apply and save gauges** updates the running display and writes `dashboard.yaml` for later sessions. Closing the gauge editor without applying discards those gauge edits. Saving rewrites YAML formatting and removes comments.

For optional reference points, open the dashboard track map, pause the video, and enable **Edit points (paused)**. Add points on the map or at the current recorded GPS location, then use **Save points** to create a separate JSON. The launcher remembers the saved points selection. Points must match the track project's reference geometry.

See [Statistics and dashboard details](Statistics-Read-Me.md) for expressions, units, intervals, playback navigation, points, and reference pictures.

## Optional: export track coordinates to CSV

Use this only when you need the coordinate CSV for a separate workflow. From PowerShell in the software folder:

```powershell
.\.venv\Scripts\python.exe trackcsv.py --input "C:\racingData\NelsonLedges.ztracks" --output "C:\racingData\NelsonLedges-track.csv"
```

For an export containing multiple tracks, list its members, then select one by its exact name:

```powershell
.\.venv\Scripts\python.exe trackcsv.py --input "C:\racingData\tracks.ztracks" --list
.\.venv\Scripts\python.exe trackcsv.py --input "C:\racingData\tracks.ztracks" --member "05b5a70l.tkk" --output "C:\racingData\track-coordinates.csv"
```

The output contains point number, latitude, longitude, inferred elevation in metres, and raw elevation. Elevation units are inferred rather than independently confirmed; zero raw elevation is treated as missing. This converter creates CSV, not JSON or YAML. See [track conversion notes](trackcsv-README.txt).

## Personal settings, backups, and updates

Back up your track data folder, including track projects, interesting points, original exports, videos, and calibration files. A GitHub clone or software ZIP does not include your racing data.

The software also saves local settings:

| File | Contents |
|---|---|
| `dashboard.yaml` | Dashboard layout and gauge settings; currently tracked by Git, so personal edits appear as repository changes |
| `last-race.json` | Launcher folder and file selections |
| `expressions.json` | Saved expressions |
| `setup-settings.json` | Machine-specific Python and video-player paths |
| `<recording>.statistics.json` beside a race CSV | Saved manually entered race interval bounds |

Before updating the software, close the analysis windows and back up personal settings, especially `dashboard.yaml`. Git users should inspect local changes before pulling updates and avoid overwriting saved preferences. ZIP users can extract an update to a separate software folder, run setup there, and deliberately transfer their personal settings and reselect their racing data. Keep `setup-settings.json` specific to the installation that generated it.

## Troubleshooting

- **Python not found or Tkinter missing:** install or modify Python with Tcl/Tk and PATH support, then rerun `Setup.cmd`.
- **Setup download or package installation fails:** check the internet connection, read `setup-log.txt`, and rerun setup.
- **Video player missing:** rerun `Setup.cmd`; it records the mpv path used by the launcher.
- **Dashboard reports no saved calibration:** calibrate that race CSV and video first.
- **Track project rejected:** choose the JSON created by **Import .ztracks...**, rather than a points JSON, coordinate CSV, or older YAML configuration.
- **No lap choices or expected channels:** inspect **Session Information** and the original AiM CSV. Lap choices depend on exported beacon metadata; expressions must use available channel names.
- **An analysis window fails:** inspect `analysis-log.txt`, `statisticsScreen-log.txt`, or `sessionInfo-log.txt` in the software folder, depending on the tool. Logs can be replaced on the next launch, so save the relevant error first.

For help, [open a GitHub issue](https://github.com/joeSparky/motorcycle-racing-analysis/issues) with the button or command used, expected behavior, and relevant error message. Remove personal information from logs or sample data before sharing them.

## Note: software folder location

Keep the software folder in its current location after setup. If you move it, rerun setup; if the Python environment no longer works, recreate `.venv` by removing that folder and running setup again. Use `Race-Analysis.cmd` for normal startup so the application uses its prepared Python environment.
