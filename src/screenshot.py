"""Static images for the README: a screenshot of the report and PNG copies of the key charts."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import charts, config, results

README_CHARTS = ["birth_year_steps", "segment_index_heatmap", "generator_check", "k_selection",
                 "targeting_scores", "seasonality_adjustment", "placebo", "follow_up"]

CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser", "chrome", "msedge",
]


def find_browser() -> str | None:
    for candidate in CANDIDATES:
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def export_charts() -> None:
    """PNG copies of the charts the README embeds, so the evidence shows without opening the report."""
    out = config.DOCS_DIR / "img"
    out.mkdir(parents=True, exist_ok=True)
    figs = charts.build_all(results.load_all())
    for name in README_CHARTS:
        figs[name].write_image(out / f"{name}.png", width=980, height=figs[name].layout.height, scale=2)
    print(f"Wrote {len(README_CHARTS)} chart images to docs/img/")


def run(width: int = 1200, height: int = 1640) -> bool:
    export_charts()
    browser = find_browser()
    target = config.DOCS_DIR / "screenshot.png"
    if browser is None:
        print("No Chrome or Edge found, skipping screenshot.")
        return False
    subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
        "--virtual-time-budget=8000", f"--screenshot={target}", (config.DOCS_DIR / "index.html").as_uri(),
    ], capture_output=True, timeout=120)
    ok = target.exists()
    print("Wrote docs/screenshot.png" if ok else "Screenshot failed, skipping.")
    return ok


if __name__ == "__main__":
    run()
