# Statistics and dashboard expressions

Open **Statistics** from Race-Analysis.cmd. Select an original AIM CSV in the launcher; no video, MPV setup or calibration is needed. A prepared track project is needed only for track-position segments. Clear the track selection to analyze a recording without track geometry.

On the statistics screen, enter a formula, choose the interval and click **Evaluate**. For example, `RPM / Speed` or `RPM / [GPS Speed]`. These use the CSV's original units; the Units box is a label, not a conversion. Comparisons such as `Throttle > 90` return 1 or 0, so their mean is the fraction of valid selected samples meeting the condition. Arithmetic, parentheses and comparisons are supported; Python functions and arbitrary code are not.

Choose a saved name and click **Save expression** to reuse a formula, units, decimal precision and histogram-bin width. Saved expressions are local to this installation in expressions.json.

## Intervals

- Entire recording includes every sample.
- Engine running includes samples with RPM strictly greater than the chosen threshold (default zero).
- Race running uses manually entered start and finish in recording seconds, inclusive. Successful evaluation saves the bounds beside the original CSV as a .statistics.json file. They are not inferred from warm-up or speed.
- Lap uses complete consecutive beacon-marker intervals from the AIM metadata. The start is included and finish excluded. Warm-up laps may be present; this numbering is not official race lap numbering. Without beacon markers, lap selection is unavailable.
- Segment of lap intersects the selected beacon lap with a track-position range. Select a saved segment or type positions. Start included, end excluded. End below start wraps around position zero. Off-track samples are excluded; 0 to the track divisions value selects the whole track.
- Time interval uses inclusive start and end in recording seconds.

The plot uses recording seconds, with toolbar zoom, pan and image saving. Excluded samples, invalid expression results and time gaps greater than one second break the line.

## Results

Mean and median use valid selected samples equally. The histogram displays counts for the same valid expression values and selected interval as the time graph. A positive Histogram bin width makes half-open bins aligned to zero (for example, width 100 gives [4000, 4100)). Zero chooses between 1 and 100 equal-width bins automatically from the valid sample count. Constant and single-sample results are supported. More than 1000 fixed-width bins is rejected; increase the width or choose automatic bins. Display rounding does not change bin membership. The histogram counts samples, rather than elapsed time.

Minimum and maximum include their recording times in seconds (the first occurrence within the selected interval when tied). Valid/omitted/selected counts and a time-weighted mean are also shown. Time weighting integrates trapezoids between adjacent valid selected samples only, excluding gaps over one second. Its included duration is displayed. This duration may be less than the requested interval because boundary interpolation is not performed. A single valid sample has no time-weighted mean. Missing channels and invalid formulas produce an error; per-sample division by zero, nonnumeric values, overflow and nonfinite results are omitted.

## Dashboard

Click **Edit gauges...**, select a gauge and enter a formula or choose a saved expression. Set its label, units, decimal places and bounds, then click **Apply and save gauge**. The running dashboard updates immediately and saves the active dashboard YAML for future runs. Select number or bar in the Display dropdown. Gauge size is preserved. Enter any desired unit conversion in the formula; applying an edited gauge removes its old conversion/scale/offset settings so conversions are not applied twice. YAML comments are removed when saving.

Open **Session Information** in the launcher to read every metadata field supplied by the original AIM CSV, including track, date, time and comments where present. Select a row to read its full value. This screen needs only the race CSV; no video, calibration or track project is required. The recording is never modified.

## Watching video while using statistics

Open Statistics and Dashboard from the same launcher, in either order. Start the video from Dashboard. Both windows stay open, and closing either one leaves the other running. Session Information can also remain open. Each screen's expression/interval changes take effect when you click Evaluate; the graph shows a red cursor at the current recording time. Click the graph to seek the video, or use Go to Min / Go to Max after evaluating. Seeking preserves the current play/pause state. While the toolbar pan or zoom tool is active, clicks operate the plot instead of seeking. Playback outside the plotted interval hides the cursor. Dashboard sync adjustments apply to statistics too.

File selections remain locked until all analysis windows close, so the open screens use the same recording. Calibration and Dashboard are mutually exclusive. Close windows with their title-bar X; redundant Done buttons have been removed. In the segment editor, SAVE SECTIONS remains the explicit save action; closing that window does not save unsaved edits.

## Adding and arranging gauges

In Edit gauges, Add Gauge creates a new entry. Enter its formula or choose a saved expression, set its label, number/bar display, units, precision and bounds. Delete Gauge removes the selected entry; Move Up and Move Down change display order. Apply and save gauges saves the whole list and updates the running dashboard. Closing the editor without applying discards gauge-list edits (saved expressions are saved separately). An empty dashboard is allowed; use Add Gauge to populate it again. The dashboard gauge area has a vertical scrollbar while playback controls stay visible.

## Track position during playback

With a prepared Track project selected in the launcher, starting the Dashboard video also opens a track map. The red dot shows the nearest recorded GPS sample, using the same calibrated time and sync adjustment as the dashboard. Seeking, stepping and pausing update the dot. The outline is the prepared reference track; the black square is its position-zero start/finish reference. North is up, with equal horizontal and vertical distance scale. The dot uses actual recorded GPS coordinates, not a snapped position on the outline. Missing/invalid GPS, data gaps over half a second from the video time and video outside the recording hide the dot. Far-off-track locations can fall outside the map view.

Close the map independently with its X. Click Track map on Dashboard to reopen it or select a prepared track if none was chosen. Closing Dashboard closes its map and video; Statistics remains independent. No aerial imagery is required.
