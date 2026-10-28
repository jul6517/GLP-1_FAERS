"""Download FAERS quarterly ASCII files from the FDA.

Source: https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html
Each quarter is one zip: faers_ascii_{YYYY}q{Q}.zip
"""

from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path

import requests

URL_TEMPLATE = "https://fis.fda.gov/content/Exports/faers_ascii_{year}q{q}.zip"


def parse_quarter(s: str) -> tuple[int, int]:
    """'2024Q1' -> (2024, 1)."""
    m = re.fullmatch(r"(\d{4})[Qq]([1-4])", s.strip())
    if not m:
        raise ValueError(f"Quarter must look like 2024Q1, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def quarter_range(start: str, end: str) -> list[str]:
    """quarter_range('2023Q3', '2024Q2') -> ['2023Q3', '2023Q4', '2024Q1', '2024Q2']."""
    y, q = parse_quarter(start)
    ey, eq = parse_quarter(end)
    if (y, q) > (ey, eq):
        raise ValueError("start quarter is after end quarter")
    out = []
    while (y, q) <= (ey, eq):
        out.append(f"{y}Q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def download_quarter(quarter: str, raw_dir: Path, retries: int = 4) -> Path:
    """Download one quarter's zip into raw_dir. Skips if already present and valid."""
    year, q = parse_quarter(quarter)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"faers_ascii_{year}q{q}.zip"

    if dest.exists() and zipfile.is_zipfile(dest):
        print(f"[skip] {dest.name} already downloaded")
        return dest

    url = URL_TEMPLATE.format(year=year, q=q)
    tmp = dest.with_suffix(".part")
    for attempt in range(retries + 1):
        try:
            print(f"[get ] {url}")
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            if not zipfile.is_zipfile(tmp):
                raise IOError(f"{url} did not return a valid zip")
            tmp.rename(dest)
            return dest
        except (requests.RequestException, IOError) as e:
            if attempt == retries:
                raise
            wait = 2 ** (attempt + 1)
            print(f"[retry] {e} -- waiting {wait}s")
            time.sleep(wait)
    return dest
