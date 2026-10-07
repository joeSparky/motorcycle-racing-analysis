Offline AiM track conversion
===========================

INSTALL ONCE
Put trackcsv.py and trackcsv.cmd together in C:\projects\tools.
Python must be installed. No additional Python packages are required.
If C:\projects\tools is on PATH, run trackcsv from any folder.

CONVERT
trackcsv --input ../racingData/nelsonLedges.ztracks --output ../racingData/nelsonLedges.csv

HELP
trackcsv -h

MULTIPLE TRACKS IN ONE EXPORT
trackcsv --input tracks.ztracks --list
Then use the exact listed member name:
trackcsv --input tracks.ztracks --member 05b5a70l.tkk --output nelsonLedges.csv

OUTPUT
point: sequential point number, starting at 1
latitude_deg / longitude_deg: signed coordinates in degrees
elevation_m_inferred: raw elevation divided by 1000; inferred metres
elevation_raw: original signed integer

Raw zero is treated as missing elevation. Missing heights are left blank.
The converter preserves the source order, including a duplicate closing point.
It does not rotate the track to start/finish, reverse it, or add section numbers.
Check point 1 and direction on the track map before using a new track configuration.

LIMITS
This decoder supports the binary pts block layout verified in the supplied
Nelson Ledges export. Other exports may differ. Unsupported layouts are rejected;
this is not a guarantee of support for every Race Studio version or track export.
The embedded block checksum is not interpreted; ZIP integrity is checked by Python.
Coordinate decoding is verified against the earlier Nelson Ledges conversion.
Elevation units have not been independently confirmed.

WORKING WITHOUT INTERNET
Everything runs on your Windows laptop. Save these files and your track exports,
reference CSVs and YAML configurations locally before leaving for the track.
