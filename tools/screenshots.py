#!/usr/bin/env python3
"""Regenerate ``assets/screenshot-*.svg`` from the dashboard as it is today.

    python tools/screenshots.py

Exists because the shipped set went stale and nobody noticed. Every one of the
five predated several rounds of fixes, and each advertised a bug the code had
since closed -- the job screen showed a ``KERNEL 192.7%`` gauge, i.e. the
impossible ratio ``model.system_cpu_fraction`` now returns ``None`` for and names
in its own comment; the overview showed the mixed-unit ``USED`` column that
``render.OVERVIEW_COLUMNS`` documents at length as removed; three showed the
invented ``30m26s`` duration format ``format_duration`` replaced with
``HH:MM:SS``. README's pitch is that this tool prints ``n/a`` rather than a
fabricated number, illustrated by a screenshot of a fabricated number.

Driven headless through Textual's own test harness against ``--demo``, so it
needs no Slurm and produces the same images on any machine. The terminal size is
the one the replaced assets were taken at -- 100x30, recoverable from their
``viewBox="0 0 1238 782"`` -- so the new files drop into the README's
``width="900"`` layout at the same aspect ratio, and 100 columns is the width the
layout tests treat as canonical.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Matches the viewBox of the assets being replaced: 1238x782 at Rich's metrics.
SIZE = (100, 30)

# (filename stem, keys to press after boot, what the shot is for)
SHOTS = [
    ("overview", [], "the ranked workload table the README leads with"),
    ("workload", ["3", "enter"], "one workload's runs"),
    ("job", ["3", "enter", "enter"], "the full post-mortem, gauges and all"),
    ("patterns", ["p"], "cross-run findings"),
    ("nodes", ["n"], "per-node failure rates"),
]


async def main() -> int:
    from slurmpast.demo import DEMO_SITE, history
    from slurmpast.site import reset_cache, site
    from slurmpast.tui import SlurmpastApp

    # Pin the synthetic cluster too, exactly as `cli._load` does under --demo:
    # otherwise the memory and GPU notes are worded from whatever cluster this
    # runs on and the images differ by machine.
    reset_cache()
    site(runner=lambda _args: DEMO_SITE)

    jobs = history()
    out = ROOT / "assets"
    for stem, keys, why in SHOTS:
        app = SlurmpastApp(lambda: list(jobs), window="synthetic demo data", no_logs=True)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.pause()
            path = out / ("screenshot-%s.svg" % stem)
            path.write_text(app.export_screenshot(title="slurmpast"))
            print("%-28s %s" % (path.relative_to(ROOT), why))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
