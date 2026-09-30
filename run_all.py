"""Rebuild everything from the raw Kaggle files.

    python run_all.py              full rebuild, then run the tests
    python run_all.py --clean      delete data/processed and outputs first
    python run_all.py --no-tests   skip pytest at the end
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time

from src import (config, download, features, generations, notebook, playbook, profile, report, screenshot,
                 segmentation, targeting, triggers)

STEPS = [
    ("Download raw data", download.download),
    ("Build SQL features", features.build),
    ("Profile the data", profile.run),
    ("Compare generations", generations.run),
    ("Segment customers", segmentation.run),
    ("Score benefit targeting", targeting.run),
    ("Backtest triggers", triggers.run),
    ("Write targeting playbook", playbook.run),
    ("Build HTML report", report.build),
    ("Execute notebook", notebook.build),
    ("Export README images", screenshot.run),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clean", action="store_true", help="delete data/processed and outputs before rebuilding")
    parser.add_argument("--no-tests", action="store_true", help="skip pytest at the end")
    args = parser.parse_args()

    if args.clean:
        for path in (config.PROCESSED_DIR, config.OUTPUT_DIR):
            shutil.rmtree(path, ignore_errors=True)
        print("Removed data/processed and outputs.")

    start = time.time()
    for i, (label, step) in enumerate(STEPS, start=1):
        t0 = time.time()
        print(f"\n[{i}/{len(STEPS)}] {label}")
        step()
        print(f"    done in {time.time() - t0:.1f}s")

    code = 0
    if not args.no_tests:
        print("\nRunning tests")
        code = subprocess.run([sys.executable, "-m", "pytest"], cwd=config.ROOT).returncode
    print(f"\nFinished in {time.time() - start:.0f}s. Open docs/index.html to read the report.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
