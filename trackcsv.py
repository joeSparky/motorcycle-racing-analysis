#!/usr/bin/env python3
"""Convert an AiM .ztracks export to an ordered track CSV, entirely offline.

Coordinates are decoded from the observed AiM pts block layout.
Elevation /1000 is inferred; raw zero is treated as missing.
Only this observed binary layout is supported; unknown layouts are rejected.
"""
import argparse
import csv
from pathlib import Path
import struct
import sys
import zipfile

FIELDS = ['point', 'latitude_deg', 'longitude_deg', 'elevation_m_inferred', 'elevation_raw']


def decode(data):
    marker = b'<hpts\x00'
    start = data.find(marker)
    if start < 0 or data.find(marker, start+1) >= 0:
        raise ValueError('Expected exactly one AiM pts block; unsupported track layout.')
    if start+12 > len(data) or data[start+10:start+12] != b'\x00>':
        raise ValueError('Unsupported pts header.')
    length = struct.unpack_from('<I', data, start+6)[0]
    end = start+12+length
    if length < 36 or length % 12 or end+8 > len(data):
        raise ValueError('Invalid or truncated pts block.')
    if data[end:end+5] != b'<pts\x00' or data[end+7:end+8] != b'>':
        raise ValueError('Unsupported pts closing marker.')
    rows = []
    for point, (lat, lon, elevation) in enumerate(
            struct.iter_unpack('<iii', data[start+12:end]), start=1):
        if not -900000000 <= lat <= 900000000 or not -1800000000 <= lon <= 1800000000:
            raise ValueError(f'Coordinate out of range at point {point}; unsupported layout.')
        rows.append([point, f'{lat/1e7:.7f}', f'{lon/1e7:.7f}',
                     '' if elevation == 0 else f'{elevation/1000:.3f}', elevation])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter,
                                    epilog="""Examples:
  trackcsv --input nelsonLedges.ztracks --output nelsonLedges.csv
  trackcsv --input tracks.ztracks --list
  trackcsv --input tracks.ztracks --member 05b5a70l.tkk -o nelsonLedges.csv

No internet or extra Python packages are required.
Point order is preserved; point 1 is not guaranteed to be start/finish for every track.
Zero raw elevations are blank in elevation_m_inferred, not filled or interpolated.""")
    parser.add_argument('file', nargs='?', type=Path, metavar='TRACK_EXPORT',
                        help='AiM .ztracks or .tkk file; alternative to --input')
    parser.add_argument('--input', type=Path, help='Track export from AiM Race Studio (not rider data)')
    parser.add_argument('-o', '--output', type=Path, help='Output CSV; default: input name with .csv extension')
    parser.add_argument('--list', action='store_true', help='List .tkk members without converting')
    parser.add_argument('--member', help='Exact .tkk member name when an archive has multiple tracks')
    if len(sys.argv) == 1:
        parser.print_help()
        return
    args = parser.parse_args()
    if args.file and args.input:
        parser.error('Use either --input or the positional file, not both.')
    source = args.input or args.file
    if source is None:
        parser.error('--input is required.')
    output = args.output or source.with_suffix('.csv')
    if not args.list and output.resolve() == source.resolve():
        parser.error('Output must differ from input.')
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            members = [info for info in archive.infolist()
                       if not info.is_dir() and info.filename.lower().endswith('.tkk')]
            if args.list:
                for info in members:
                    print(info.filename)
                if not members:
                    raise ValueError('Archive has no .tkk tracks.')
                return
            if args.member:
                members = [info for info in members if info.filename == args.member]
            if len(members) != 1:
                raise ValueError('Select exactly one track with --member; use --list to see names.')
            if members[0].file_size > 32 * 1024 * 1024:
                raise ValueError('Track member exceeds 32 MiB.')
            rows = decode(archive.read(members[0]))
    elif source.suffix.lower() == '.tkk':
        if args.member or args.list:
            parser.error('--member and --list apply only to archives.')
        rows = decode(source.read_bytes())
    else:
        raise ValueError('Input is not a ZIP-based .ztracks export or a .tkk file.')
    with output.open('w', newline='', encoding='utf-8') as target:
        writer = csv.writer(target)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    print(f'{output}: {len(rows)} track points.')
    print('Elevation metres are inferred from raw /1000; raw zero is treated as missing.',
          file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, struct.error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f'trackcsv.py: error: {exc}', file=sys.stderr)
        sys.exit(2)
