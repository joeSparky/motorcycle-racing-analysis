# Statistics and dashboard expressions

Open **Statistics** from Race-Analysis.cmd. Select an original AIM CSV in the launcher; no video, MPV setup or calibration is needed. A prepared track project is needed only for track-position segments. Clear the track selection to analyze a recording without track geometry.

On the statistics screen, enter a formula, choose the interval and click **Evaluate**. For example, `RPM / Speed` or `RPM / [GPS Speed]`. These use the CSV's original units; the Units box is a label, not a conversion. Comparisons such as `Throttle > 90` return 1 or 0, so their mean is the fraction of valid selected samples meeting the condition. Arithmetic, parentheses and comparisons are supported; Python functions and arbitrary code are not.

Choose a saved name and click **Save expression** to reuse a formula, units, decimal precision and mode-bin width. Saved expressions are local to this installation in expressions.json.

## Intervals

- Entire recording includes every sample.
- Engine running includes samples with RPM strictly greater than the chosen threshold (default zero).
- Race running uses manually entered start and finish in recording seconds, inclusive. Successful evaluation saves the bounds beside the original CSV as a .statistics.json file. They are not inferred from warm-up or speed.
- Lap uses complete consecutive beacon-marker intervals from the AIM metadata. The start is included and finish excluded. Warm-up laps may be present; this numbering is not official race lap numbering. Without beacon markers, lap selection is unavailable.
- Segment of lap intersects the selected beacon lap with a track-position range. Select a saved segment or type positions. Start included, end excluded. End below start wraps around position zero. Off-track samples are excluded; 0 to the track divisions value selects the whole track.
- Time interval uses inclusive start and end in recording seconds.

The plot uses recording seconds, with toolbar zoom, pan and image saving. Excluded samples, invalid expression results and time gaps greater than one second break the line.

## Results

Mean and median use valid selected samples equally. Mode width zero means exact values. A positive width groups values into half-open bins aligned to zero (for example, width 100 means [4000, 4100)). Tied modes are identified; if every value/bin occurs once there is no repeated mode. Display rounding does not change calculations or bin membership.

Minimum and maximum include their recording times in seconds (the first occurrence within the selected interval when tied). Valid/omitted/selected counts and a time-weighted mean are also shown. Time weighting integrates trapezoids between adjacent valid selected samples only, excluding gaps over one second. Its included duration is displayed. This duration may be less than the requested interval because boundary interpolation is not performed. A single valid sample has no time-weighted mean. Missing channels and invalid formulas produce an error; per-sample division by zero, nonnumeric values, overflow and nonfinite results are omitted.

## Dashboard

Click **Edit gauges...**, select a gauge and enter a formula or choose a saved expression. Set its label, units, decimal places and bounds, then click **Apply and save gauge**. The running dashboard updates immediately and saves the active dashboard YAML for future runs. Select number or bar in the Display dropdown. Gauge size is preserved. Enter any desired unit conversion in the formula; applying an edited gauge removes its old conversion/scale/offset settings so conversions are not applied twice. YAML comments are removed when saving.

Open **Session Information** in the launcher to read every metadata field supplied by the original AIM CSV, including track, date, time and comments where present. Select a row to read its full value. This screen needs only the race CSV; no video, calibration or track project is required. The recording is never modified.

## Watching video while using statistics

Open Statistics and Dashboard from the same launcher, in either order. Start the video from Dashboard. Both windows stay open, and closing either one leaves the other running. Session Information can also remain open. Each screen's expression/interval changes take effect when you click Evaluate; the statistics plot does not yet track the moving video position or seek it.

File selections remain locked until all analysis windows close, so the open screens use the same recording. Calibration and Dashboard are mutually exclusive. Close windows with their title-bar X; redundant Done buttons have been removed. In the segment editor, SAVE SECTIONS remains the explicit save action; closing that window does not save unsaved edits.
