"""Download the Kaggle dataset into data/raw/ using the Kaggle CLI."""
from __future__ import annotations

import subprocess
import sys

from . import config

CREDENTIAL_HELP = """
Kaggle download failed. This usually means credentials are missing.

1. Sign in at https://www.kaggle.com, open Settings, and create an API token.
2. Either save the downloaded kaggle.json to ~/.kaggle/kaggle.json
   (on Windows: C:\\Users\\<you>\\.kaggle\\kaggle.json),
   or set the KAGGLE_USERNAME and KAGGLE_KEY environment variables.
   Newer tokens also work as ~/.kaggle/access_token or KAGGLE_API_TOKEN.
3. Run this again: python run_all.py
"""


def have_raw_files() -> bool:
    return all((config.RAW_DIR / name).exists() for name in config.RAW_FILES)


def download(force: bool = False) -> None:
    if have_raw_files() and not force:
        print(f"Raw files already in {config.RAW_DIR}, skipping download.")
        return
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "kaggle", "datasets", "download",
        "-d", config.KAGGLE_DATASET, "-p", str(config.RAW_DIR), "--unzip", "--quiet",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not have_raw_files():
        print(result.stdout, result.stderr, sep="\n")
        raise SystemExit(CREDENTIAL_HELP)
    print(f"Downloaded {config.KAGGLE_DATASET} to {config.RAW_DIR}")


if __name__ == "__main__":
    download(force="--force" in sys.argv)
