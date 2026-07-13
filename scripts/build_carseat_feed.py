#!/usr/bin/env python3
"""Build the HomeKeeper car-seat recall feed.

Child car seat recalls are NHTSA jurisdiction and have no searchable REST
endpoint. NHTSA publishes them inside a bulk flat file; this script downloads
it, filters to child-seat records (RCLTYPECD == 'C'), and emits a small JSON
the iOS app fetches from GitHub Pages.

Stdlib only. Fails loudly (non-zero exit) rather than publishing garbage.
"""

import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

FLAT_FILE_URL = "https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip"
OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "carseat-recalls.json"

# Column layout per NHTSA's RCL.txt readme (0-indexed, tab-separated):
COL_CAMPNO = 1        # NHTSA campaign number, e.g. 24C001000
COL_MAKETXT = 2       # brand for child seats
COL_MODELTXT = 3      # model
COL_BGMAN = 8         # begin manufacture date, yyyymmdd
COL_ENDMAN = 9        # end manufacture date, yyyymmdd
COL_RCLTYPECD = 10    # V=vehicle, E=equipment, T=tire, C=child seat
COL_RCDATE = 15       # report received date, yyyymmdd
COL_DESC_DEFECT = 19
COL_CONSEQUENCE = 20
COL_CORRECTIVE = 21

CAMPNO_RE = re.compile(r"^\d{2}[CEVT]\d{6}$")
MAX_TEXT = 500
STALE_REFRESH_DAYS = 6


def parse_yyyymmdd(raw: str) -> str | None:
    raw = raw.strip()
    if len(raw) != 8 or not raw.isdigit() or raw.startswith("9999"):
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def clean(text: str) -> str | None:
    text = text.strip()
    return text[:MAX_TEXT] if text else None


def main() -> int:
    print(f"Downloading {FLAT_FILE_URL}")
    request = urllib.request.Request(
        FLAT_FILE_URL, headers={"User-Agent": "homekeeper-data feed builder"})
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = response.read()
    print(f"Downloaded {len(payload) / 1_000_000:.1f} MB")

    archive = zipfile.ZipFile(io.BytesIO(payload))
    txt_names = [n for n in archive.namelist() if n.lower().endswith(".txt")]
    if not txt_names:
        print("ERROR: no .txt member in zip", file=sys.stderr)
        return 1

    entries = {}
    total_rows = 0
    campno_ok = 0
    for name in txt_names:
        with archive.open(name) as fh:
            for raw_line in io.TextIOWrapper(fh, encoding="latin-1"):
                fields = raw_line.rstrip("\n").split("\t")
                if len(fields) < COL_CORRECTIVE + 1:
                    continue
                total_rows += 1
                if CAMPNO_RE.match(fields[COL_CAMPNO].strip()):
                    campno_ok += 1
                if fields[COL_RCLTYPECD].strip() != "C":
                    continue
                campno = fields[COL_CAMPNO].strip()
                brand = fields[COL_MAKETXT].strip()
                model = fields[COL_MODELTXT].strip()
                key = (campno, brand, model)
                if key in entries:
                    continue
                entries[key] = {
                    "campaignNumber": campno,
                    "brand": brand or None,
                    "model": model or None,
                    "manufacturedFrom": parse_yyyymmdd(fields[COL_BGMAN]),
                    "manufacturedTo": parse_yyyymmdd(fields[COL_ENDMAN]),
                    "defect": clean(fields[COL_DESC_DEFECT]),
                    "consequence": clean(fields[COL_CONSEQUENCE]),
                    "remedy": clean(fields[COL_CORRECTIVE]),
                    "recallDate": parse_yyyymmdd(fields[COL_RCDATE]),
                    "url": f"https://www.nhtsa.gov/recalls?nhtsaId={campno}",
                }

    # Sanity gates: if the column layout shifted, campaign numbers won't look
    # like campaign numbers. Refuse to publish garbage.
    if total_rows < 1000:
        print(f"ERROR: only {total_rows} rows parsed — layout change?", file=sys.stderr)
        return 1
    if campno_ok / total_rows < 0.5:
        print("ERROR: campaign-number column failed validation — column order changed?",
              file=sys.stderr)
        return 1
    if not entries:
        print("ERROR: zero child-seat records — RCLTYPECD column changed?", file=sys.stderr)
        return 1

    recalls = sorted(entries.values(),
                     key=lambda e: (e["recallDate"] or "", e["campaignNumber"]),
                     reverse=True)
    print(f"{len(recalls)} child-seat recall entries from {total_rows} rows")

    # Skip the commit churn when nothing changed and the feed is fresh.
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text())
            generated = datetime.fromisoformat(existing.get("generatedAt", "1970-01-01T00:00:00+00:00"))
            age_days = (datetime.now(timezone.utc) - generated).days
            if existing.get("recalls") == recalls and age_days < STALE_REFRESH_DAYS:
                print("No changes and feed is fresh — not rewriting.")
                return 0
        except (ValueError, KeyError):
            pass

    feed = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recalls": recalls,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(feed, indent=1) + "\n")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1000:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
