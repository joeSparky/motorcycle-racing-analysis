#!/usr/bin/env python3
"""Extract sample CSV from an AIM export, one record at a time.

Reads stdin unless a filename is supplied; writes CSV to stdout.
Removes leading metadata, the units record, and blank records. Preserves
channel names and sample values. Malformed samples stop processing with an
error on stderr (exit code 2); output before that error may already be written.
--metadata outputs metadata instead; --units outputs Channel,Unit CSV.
"""
import argparse
import csv
import math
import sys


def extract(source, target, mode='data'):
    reader = csv.reader(source, strict=True)
    writer = csv.writer(target, lineterminator='\n')
    previous = None
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        if (previous is not None and len(previous) >= 2
                and previous[0].strip() == 'Time'
                and row[0].strip().lower() in {'s', 'sec', 'second', 'seconds'}):
            header, units = previous, row
            break
        if previous is not None and mode == 'metadata':
            writer.writerow(previous)
        previous = row
    else:
        raise ValueError("Could not locate AIM channel header followed by a units record beginning with 's'.")

    if len(units) != len(header):
        raise ValueError(f'Line {reader.line_num}: units record has {len(units)} fields; expected {len(header)}.')
    if len(set(header)) != len(header) or any(not name.strip() for name in header):
        raise ValueError('Channel names must be nonblank and unique.')
    if mode == 'metadata':
        return
    if mode == 'units':
        writer.writerow(['Channel', 'Unit'])
        writer.writerows(zip(header, units))
        return

    writer.writerow(['Record'] + header)
    record_number = 0
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(header):
            raise ValueError(f'Line {reader.line_num}: sample has {len(row)} fields; expected {len(header)}.')
        try:
            valid_time = math.isfinite(float(row[0]))
        except ValueError:
            valid_time = False
        if not valid_time:
            raise ValueError(f'Line {reader.line_num}: sample Time must be a finite number.')
        record_number += 1
        writer.writerow([record_number] + row)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--metadata', action='store_true', help='Output leading metadata as CSV')
    modes.add_argument('--units', action='store_true', help='Output channel names and units as CSV')
    parser.add_argument('file', nargs='?', help='AIM CSV filename; omit for stdin')
    args = parser.parse_args()
    mode = 'metadata' if args.metadata else 'units' if args.units else 'data'
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(newline='')
    if args.file:
        with open(args.file, newline='', encoding='utf-8-sig') as source:
            extract(source, sys.stdout, mode)
    else:
        # File input strips a UTF-8 BOM via its encoding; stdin needs the same treatment.
        def lines():
            for index, line in enumerate(sys.stdin):
                yield line.lstrip('\ufeff') if index == 0 else line
        extract(lines(), sys.stdout, mode)


if __name__ == '__main__':
    try:
        main()
    except BrokenPipeError:
        # A consumer such as Select-Object -First may finish before we do.
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
    except (OSError, ValueError, csv.Error) as exc:
        print(f'aimcsv: error: {exc}', file=sys.stderr)
        sys.exit(2)

