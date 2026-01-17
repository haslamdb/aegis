#!/usr/bin/env python3
"""Shift dates in Synthea FHIR bundles to be recent.

Synthea generates complete patient histories with dates spanning years.
This script shifts all dates so the most recent events are near "now",
making the data suitable for testing real-time alerting systems.

Usage:
    python shift_synthea_dates.py data/synthea/fhir/
    python shift_synthea_dates.py data/synthea/fhir/ --output data/synthea/fhir-recent/
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_datetime(dt_str: str) -> datetime | None:
    """Parse FHIR datetime string to datetime object."""
    if not dt_str:
        return None

    # Handle various FHIR datetime formats
    patterns = [
        "%Y-%m-%dT%H:%M:%S%z",      # Full with timezone
        "%Y-%m-%dT%H:%M:%S.%f%z",   # With microseconds
        "%Y-%m-%dT%H:%M:%S",        # No timezone
        "%Y-%m-%d",                  # Date only
    ]

    # Normalize timezone format (replace -04:00 with -0400)
    dt_str_normalized = re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', dt_str)

    for pattern in patterns:
        try:
            dt = datetime.strptime(dt_str_normalized, pattern)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


def format_datetime(dt: datetime, original_format: str) -> str:
    """Format datetime back to FHIR format, preserving original style."""
    if "T" not in original_format:
        # Date only
        return dt.strftime("%Y-%m-%d")

    # Full datetime
    result = dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Add timezone
    tz_offset = dt.strftime("%z")
    if tz_offset:
        # Format as -04:00 instead of -0400
        result += f"{tz_offset[:3]}:{tz_offset[3:]}"

    return result


def find_max_date(bundle: dict) -> datetime | None:
    """Find the most recent date in a bundle."""
    max_date = None

    def check_value(value):
        nonlocal max_date
        if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}', value):
            dt = parse_datetime(value)
            if dt and (max_date is None or dt > max_date):
                max_date = dt
        elif isinstance(value, dict):
            for v in value.values():
                check_value(v)
        elif isinstance(value, list):
            for item in value:
                check_value(item)

    check_value(bundle)
    return max_date


def shift_dates(obj, time_delta: timedelta, now: datetime):
    """Recursively shift all dates in an object by the given timedelta."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}', value):
                dt = parse_datetime(value)
                if dt:
                    new_dt = dt + time_delta
                    # Don't shift into the future
                    if new_dt > now:
                        new_dt = now - timedelta(hours=1)
                    result[key] = format_datetime(new_dt, value)
                else:
                    result[key] = value
            else:
                result[key] = shift_dates(value, time_delta, now)
        return result
    elif isinstance(obj, list):
        return [shift_dates(item, time_delta, now) for item in obj]
    else:
        return obj


def process_bundle(bundle: dict, target_recent_hours: int = 72) -> dict:
    """Process a bundle to shift dates so recent events are near now."""
    now = datetime.now(timezone.utc)
    max_date = find_max_date(bundle)

    if max_date is None:
        return bundle

    # Calculate shift needed to make max_date be target_recent_hours ago
    target_max = now - timedelta(hours=target_recent_hours)
    time_delta = target_max - max_date

    return shift_dates(bundle, time_delta, now)


def process_file(input_path: Path, output_path: Path, target_hours: int):
    """Process a single FHIR bundle file."""
    with open(input_path) as f:
        bundle = json.load(f)

    processed = process_bundle(bundle, target_hours)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(processed, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Shift dates in Synthea FHIR bundles to be recent",
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing FHIR bundle JSON files",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory (default: overwrite input files)",
    )
    parser.add_argument(
        "--hours", "-H",
        type=int,
        default=72,
        help="Target hours ago for most recent events (default: 72)",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output) if args.output else input_dir

    if not input_dir.exists():
        print(f"Error: {input_dir} does not exist")
        return 1

    json_files = list(input_dir.glob("*.json"))
    print(f"Processing {len(json_files)} files...")

    for i, json_file in enumerate(json_files, 1):
        output_file = output_dir / json_file.name
        process_file(json_file, output_file, args.hours)

        if i % 10 == 0 or i == len(json_files):
            print(f"  Processed {i}/{len(json_files)} files")

    print(f"\nDone. Files written to {output_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
