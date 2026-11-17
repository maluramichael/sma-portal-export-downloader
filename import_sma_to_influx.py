#!/usr/bin/env python3
"""
Import SMA ONLINE5M ZIP exports into InfluxDB.
Reads CSV data from ZIP files, converts to InfluxDB line protocol, and bulk-writes.

Usage:
    python3 import_sma_to_influx.py [--dry-run] [--from DATE] [--to DATE] [--data-dir DIR]

Configuration through environment variables:
    INFLUX_URL   write endpoint, default http://localhost:8086/write
    INFLUX_DB    database, default sma
    INFLUX_USER, INFLUX_PASS   basic auth, both optional
    SMA_DATA_DIR  base directory of download_sma.py (reads <dir>/ONLINE5M), default ./data

Examples:
    python3 import_sma_to_influx.py                    # Import all
    python3 import_sma_to_influx.py --dry-run           # Preview without writing
    python3 import_sma_to_influx.py --from 2024-01-01   # Import from date
"""

import os
import sys
import argparse
import time
from datetime import datetime
from zipfile import ZipFile, BadZipFile
import requests

DATA_DIR = os.path.join(os.environ.get("SMA_DATA_DIR", "data"), "ONLINE5M")
INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086/write")
INFLUX_DB = os.environ.get("INFLUX_DB", "sma")
INFLUX_AUTH = (os.environ["INFLUX_USER"], os.environ.get("INFLUX_PASS", "")) if os.environ.get("INFLUX_USER") else None
BATCH_SIZE = 5000  # lines per InfluxDB write

# Map CSV column names to InfluxDB measurements
# We pick the most useful columns to avoid bloating the DB
COLUMN_MAP = {
    # Grid power
    "GridMs.TotW.Avg":       ("gridms_totw_avg", None),
    "GridMs.TotW.Max":       ("gridms_totw_max", None),
    "GridMs.TotW.Min":       ("gridms_totw_min", None),
    # Grid phases (W)
    "GridMs.W.phsA.Avg":     ("gridms_w_phsa_avg", None),
    "GridMs.W.phsA.Max":     ("gridms_w_phsa_max", None),
    "GridMs.W.phsA.Min":     ("gridms_w_phsa_min", None),
    "GridMs.W.phsB.Avg":     ("gridms_w_phsb_avg", None),
    "GridMs.W.phsB.Max":     ("gridms_w_phsb_max", None),
    "GridMs.W.phsB.Min":     ("gridms_w_phsb_min", None),
    "GridMs.W.phsC.Avg":     ("gridms_w_phsc_avg", None),
    "GridMs.W.phsC.Max":     ("gridms_w_phsc_max", None),
    "GridMs.W.phsC.Min":     ("gridms_w_phsc_min", None),
    # Grid voltage (cV -> V, divide by 100... but SMA CSV already outputs V)
    "GridMs.PhV.phsA.Avg":   ("gridms_phv_phsa_avg", None),
    "GridMs.PhV.phsA.Max":   ("gridms_phv_phsa_max", None),
    "GridMs.PhV.phsA.Min":   ("gridms_phv_phsa_min", None),
    "GridMs.PhV.phsB.Avg":   ("gridms_phv_phsb_avg", None),
    "GridMs.PhV.phsB.Max":   ("gridms_phv_phsb_max", None),
    "GridMs.PhV.phsB.Min":   ("gridms_phv_phsb_min", None),
    "GridMs.PhV.phsC.Avg":   ("gridms_phv_phsc_avg", None),
    "GridMs.PhV.phsC.Max":   ("gridms_phv_phsc_max", None),
    "GridMs.PhV.phsC.Min":   ("gridms_phv_phsc_min", None),
    # Grid current (A)
    "GridMs.A.phsA.Avg":     ("gridms_a_phsa_avg", None),
    "GridMs.A.phsA.Max":     ("gridms_a_phsa_max", None),
    "GridMs.A.phsA.Min":     ("gridms_a_phsa_min", None),
    "GridMs.A.phsB.Avg":     ("gridms_a_phsb_avg", None),
    "GridMs.A.phsB.Max":     ("gridms_a_phsb_max", None),
    "GridMs.A.phsB.Min":     ("gridms_a_phsb_min", None),
    "GridMs.A.phsC.Avg":     ("gridms_a_phsc_avg", None),
    "GridMs.A.phsC.Max":     ("gridms_a_phsc_max", None),
    "GridMs.A.phsC.Min":     ("gridms_a_phsc_min", None),
    # Grid frequency
    "GridMs.Hz.Avg":         ("gridms_hz_avg", None),
    "GridMs.Hz.Max":         ("gridms_hz_max", None),
    "GridMs.Hz.Min":         ("gridms_hz_min", None),
    # Total grid current
    "GridMs.TotA.Avg":       ("gridms_tota_avg", None),
    "GridMs.TotA.Max":       ("gridms_tota_max", None),
    "GridMs.TotA.Min":       ("gridms_tota_min", None),
    # DC strings (both naming conventions: old [A]/[B] and new StrA/StrB)
    "DcMs.Watt[A].Avg":      ("dcms_watt_stra_avg", None),
    "DcMs.Watt[A].Max":      ("dcms_watt_stra_max", None),
    "DcMs.Watt[A].Min":      ("dcms_watt_stra_min", None),
    "DcMs.Watt[B].Avg":      ("dcms_watt_strb_avg", None),
    "DcMs.Watt[B].Max":      ("dcms_watt_strb_max", None),
    "DcMs.Watt[B].Min":      ("dcms_watt_strb_min", None),
    "DcMs.Watt.StrA.Avg":    ("dcms_watt_stra_avg", None),
    "DcMs.Watt.StrA.Max":    ("dcms_watt_stra_max", None),
    "DcMs.Watt.StrA.Min":    ("dcms_watt_stra_min", None),
    "DcMs.Watt.StrB.Avg":    ("dcms_watt_strb_avg", None),
    "DcMs.Watt.StrB.Max":    ("dcms_watt_strb_max", None),
    "DcMs.Watt.StrB.Min":    ("dcms_watt_strb_min", None),
    "DcMs.Vol[A].Avg":       ("dcms_vol_stra_avg", None),
    "DcMs.Vol[A].Max":       ("dcms_vol_stra_max", None),
    "DcMs.Vol[A].Min":       ("dcms_vol_stra_min", None),
    "DcMs.Vol[B].Avg":       ("dcms_vol_strb_avg", None),
    "DcMs.Vol[B].Max":       ("dcms_vol_strb_max", None),
    "DcMs.Vol[B].Min":       ("dcms_vol_strb_min", None),
    "DcMs.Vol.StrA.Avg":     ("dcms_vol_stra_avg", None),
    "DcMs.Vol.StrA.Max":     ("dcms_vol_stra_max", None),
    "DcMs.Vol.StrA.Min":     ("dcms_vol_stra_min", None),
    "DcMs.Vol.StrB.Avg":     ("dcms_vol_strb_avg", None),
    "DcMs.Vol.StrB.Max":     ("dcms_vol_strb_max", None),
    "DcMs.Vol.StrB.Min":     ("dcms_vol_strb_min", None),
    "DcMs.Amp[A].Avg":       ("dcms_amp_stra_avg", None),
    "DcMs.Amp[A].Max":       ("dcms_amp_stra_max", None),
    "DcMs.Amp[A].Min":       ("dcms_amp_stra_min", None),
    "DcMs.Amp[B].Avg":       ("dcms_amp_strb_avg", None),
    "DcMs.Amp[B].Max":       ("dcms_amp_strb_max", None),
    "DcMs.Amp[B].Min":       ("dcms_amp_strb_min", None),
    "DcMs.Amp.StrA.Avg":     ("dcms_amp_stra_avg", None),
    "DcMs.Amp.StrA.Max":     ("dcms_amp_stra_max", None),
    "DcMs.Amp.StrA.Min":     ("dcms_amp_stra_min", None),
    "DcMs.Amp.StrB.Avg":     ("dcms_amp_strb_avg", None),
    "DcMs.Amp.StrB.Max":     ("dcms_amp_strb_max", None),
    "DcMs.Amp.StrB.Min":     ("dcms_amp_strb_min", None),
    # PV generation
    "PvGen.PvW.Avg":         ("pvgen_pvw_avg", None),
    "PvGen.PvW.Max":         ("pvgen_pvw_max", None),
    "PvGen.PvW.Min":         ("pvgen_pvw_min", None),
    # Isolation
    "Isolation.FltA.Avg":    ("isolation_flta_avg", None),
    "Isolation.FltA.Max":    ("isolation_flta_max", None),
    "Isolation.FltA.Min":    ("isolation_flta_min", None),
    # Apparent/reactive power
    "GridMs.TotVA.Avg":      ("gridms_totva_avg", None),
    "GridMs.TotVA.Max":      ("gridms_totva_max", None),
    "GridMs.TotVA.Min":      ("gridms_totva_min", None),
    "GridMs.TotVAr.Avg":     ("gridms_totvar_avg", None),
    "GridMs.TotVAr.Max":     ("gridms_totvar_max", None),
    "GridMs.TotVAr.Min":     ("gridms_totvar_min", None),
    # Power factor
    "GridMs.TotPFPrc.Avg":   ("gridms_totpfprc_avg", None),
    "GridMs.TotPFPrc.Max":   ("gridms_totpfprc_max", None),
    "GridMs.TotPFPrc.Min":   ("gridms_totpfprc_min", None),
    # Phase apparent power
    "GridMs.VA.phsA.Avg":    ("gridms_va_phsa_avg", None),
    "GridMs.VA.phsA.Max":    ("gridms_va_phsa_max", None),
    "GridMs.VA.phsA.Min":    ("gridms_va_phsa_min", None),
    "GridMs.VA.phsB.Avg":    ("gridms_va_phsb_avg", None),
    "GridMs.VA.phsB.Max":    ("gridms_va_phsb_max", None),
    "GridMs.VA.phsB.Min":    ("gridms_va_phsb_min", None),
    "GridMs.VA.phsC.Avg":    ("gridms_va_phsc_avg", None),
    "GridMs.VA.phsC.Max":    ("gridms_va_phsc_max", None),
    "GridMs.VA.phsC.Min":    ("gridms_va_phsc_min", None),
    # Phase reactive power
    "GridMs.VAr.phsA.Avg":   ("gridms_var_phsa_avg", None),
    "GridMs.VAr.phsA.Max":   ("gridms_var_phsa_max", None),
    "GridMs.VAr.phsA.Min":   ("gridms_var_phsa_min", None),
    "GridMs.VAr.phsB.Avg":   ("gridms_var_phsb_avg", None),
    "GridMs.VAr.phsB.Max":   ("gridms_var_phsb_max", None),
    "GridMs.VAr.phsB.Min":   ("gridms_var_phsb_min", None),
    "GridMs.VAr.phsC.Avg":   ("gridms_var_phsc_avg", None),
    "GridMs.VAr.phsC.Max":   ("gridms_var_phsc_max", None),
    "GridMs.VAr.phsC.Min":   ("gridms_var_phsc_min", None),
    # DC voltage max
    "DcMs.VolMax[A].Avg":    ("dcms_volmax_stra_avg", None),
    "DcMs.VolMax[A].Max":    ("dcms_volmax_stra_max", None),
    "DcMs.VolMax[A].Min":    ("dcms_volmax_stra_min", None),
    "DcMs.VolMax[B].Avg":    ("dcms_volmax_strb_avg", None),
    "DcMs.VolMax[B].Max":    ("dcms_volmax_strb_max", None),
    "DcMs.VolMax[B].Min":    ("dcms_volmax_strb_min", None),
}


def parse_timestamp(date_str):
    """Parse SMA date format to unix timestamp in seconds."""
    dt = datetime.strptime(date_str.strip(), "%d.%m.%Y %H:%M:%S")
    return int(dt.timestamp())


def parse_csv_from_zip(zip_path):
    """Extract CSV data from a ZIP and return InfluxDB line protocol lines."""
    lines = []

    try:
        z = ZipFile(zip_path)
    except BadZipFile:
        print(f"  SKIP (bad zip): {zip_path}", file=sys.stderr)
        return lines

    # Process ALL files in the ZIP (CSV and numbered files like .001, .002 etc.)
    # They all share the same format. The .CSV is a summary, .001-.00N are chunks.
    all_files = sorted(z.namelist())

    col_map = None

    for entry_name in all_files:
        with z.open(entry_name) as f:
            raw = f.read().decode('utf-8', errors='replace')

        # Handle both CRLF and LF line endings
        content = raw.replace('\r\n', '\n').split('\n')

        if len(content) < 9:
            continue

        # Line 5 = column names (first column is empty = DateTime)
        # Only parse columns once (all files in a ZIP have the same structure)
        if col_map is None:
            columns = content[5].split(',')
            col_map = {}
            for i, col_name in enumerate(columns):
                col_name = col_name.strip()
                if col_name in COLUMN_MAP:
                    col_map[i] = COLUMN_MAP[col_name]

        # Data starts at line 8
        for row_str in content[8:]:
            row = row_str.split(',')
            if len(row) < 2 or not row[0].strip():
                continue

            try:
                ts = parse_timestamp(row[0])
            except (ValueError, IndexError):
                continue

            for col_idx, (measurement, _) in col_map.items():
                if col_idx >= len(row):
                    continue
                val = row[col_idx].strip()
                if val == '' or val == 'nan' or val == 'NaN':
                    continue
                try:
                    float(val)  # validate
                except ValueError:
                    continue
                lines.append(f"{measurement},source=pv value={val} {ts}")

    return lines


def write_to_influx(lines, dry_run=False):
    """Write lines to InfluxDB in batches."""
    total = len(lines)
    written = 0

    for i in range(0, total, BATCH_SIZE):
        batch = lines[i:i + BATCH_SIZE]
        payload = "\n".join(batch)

        if dry_run:
            written += len(batch)
            continue

        r = requests.post(
            INFLUX_URL,
            params={"db": INFLUX_DB, "precision": "s"},
            auth=INFLUX_AUTH,
            data=payload
        )
        if r.status_code == 204:
            written += len(batch)
        else:
            print(f"  InfluxDB error: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return written

    return written


def main():
    parser = argparse.ArgumentParser(description="Import SMA ONLINE5M ZIPs to InfluxDB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--data-dir", help="directory with the ZIP files (default <SMA_DATA_DIR>/ONLINE5M)")
    args = parser.parse_args()

    global DATA_DIR
    DATA_DIR = args.data_dir or DATA_DIR

    from_date = datetime.strptime(args.from_date, "%Y-%m-%d") if args.from_date else None
    to_date = datetime.strptime(args.to_date, "%Y-%m-%d") if args.to_date else None

    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith('.ZIP'))

    # Filter by date range
    filtered = []
    for f in files:
        try:
            file_date = datetime.strptime(f[2:8], "%y%m%d")
            if from_date and file_date < from_date:
                continue
            if to_date and file_date > to_date:
                continue
            filtered.append(f)
        except ValueError:
            continue

    print(f"Importing {len(filtered)} ZIP files {'(DRY RUN)' if args.dry_run else ''}")
    total_lines = 0
    total_written = 0
    start_time = time.time()

    for i, f in enumerate(filtered):
        zip_path = os.path.join(DATA_DIR, f)
        lines = parse_csv_from_zip(zip_path)
        total_lines += len(lines)

        if lines:
            written = write_to_influx(lines, dry_run=args.dry_run)
            total_written += written

        if (i + 1) % 50 == 0 or i == len(filtered) - 1:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(filtered) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(filtered)}] {total_written:,} points written, "
                  f"{rate:.1f} files/s, ~{remaining:.0f}s remaining")

    elapsed = time.time() - start_time
    print(f"\nDone: {total_written:,} / {total_lines:,} points from {len(filtered)} files in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
