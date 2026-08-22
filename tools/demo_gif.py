#!/usr/bin/env python3
"""Regenerate ``assets/demo.gif``, the README's lead image.

    python tools/demo_gif.py

Walks the same storyline as ``assets/demo.tape`` — overview, filter to the
problems, into a workload, into one job's post-mortem, cross-run patterns, node
reliability — against ``--demo``, so it needs no Slurm and renders the same on
any machine.

**Why this exists rather than just the tape.** `assets/demo.tape` needs `vhs`,
`ttyd` and `ffmpeg`, none of which are installable everywhere, and the result was
that `assets/demo.gif` was *never committed at all*: README pointed at
`raw.githubusercontent.com/.../assets/demo.gif` from the very first commit and
that URL has always 404'd. A build step nobody can run is a build step that does
not happen, so this one uses installable Python packages only — Textual to drive
the app, `cairosvg` to rasterize, Pillow to assemble:

    pip install -e ".[assets]"

Those last two live in their own extra rather than in `dev`, because cairosvg pulls
a native cairo and CI installs `[dev]` six times over without ever rendering a GIF.
They were in NO extra at all for several rounds while this docstring claimed a dev
install brought them in, so the command above failed with ModuleNotFoundError on
exactly the clean checkout it is written for — the same shape of failure as the tape
it replaced.

The rasterizing step pins a locally-installed monospace face. Textual's SVG export
names Fira Code and reaches for it over a CDN, which is not there offline; without
a pin the fallback is proportional and every column in every table drifts out of
line, which for a tool whose whole output is tables makes the image worse than no
image.

The tape is kept for anyone who has the toolchain and wants real keystroke
animation. If you change one, change the other: they are two recordings of one
story.
"""

from __future__ import annotations

import asyncio
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# The terminal the screenshots are taken at, so the two asset sets match.
SIZE = (100, 30)
# Rendered width in pixels. README displays it at 900; the extra is for HiDPI.
PIXEL_WIDTH = 1240

# A monospace face that is actually on disk. Anything here works as long as it is
# genuinely fixed-width -- Textual positions each styled run at a column computed
# from the advance width, so a proportional fallback shears every table.
MONO = "DejaVu Sans Mono"

# (keys to press before capturing, milliseconds to hold the frame). The beats and
# their timings come from assets/demo.tape.
BEATS = [
    ([], 3000),  # 1. the ranked workload table
    (["down"], 500),
    (["down"], 500),
    (["down"], 1200),
    (["f"], 2500),  # 2. filter to the problems
    # 3. the hung workload. The tape says "3", which was its rank in the UNFILTERED
    # list; after `f` that row is ddp-pretrain, a single run, and the demo spent its
    # two best beats on the least interesting workload it has. cot-exp is 2 here.
    (["2"], 700),
    (["enter"], 2500),
    # Onto a run that hung rather than the one that squeezed through. The newest
    # cot-exp run is a COMPLETED one, so opening row 1 spent the demo's longest
    # beat on a post-mortem reading "nothing to flag" -- in the workload whose
    # entire purpose here is the hang.
    (["down"], 700),
    (["enter"], 3000),  # 4. one job: the full post-mortem
    # ...and down to the findings, which is the answer the whole tool exists to
    # give. They sit below the fold on a 30-row terminal, so the tape's version of
    # this beat showed the measurements and never the diagnosis.
    (["end"], 4000),
    (["escape"], 900),
    (["escape"], 900),
    (["p"], 4500),  # 5. cross-run patterns
    (["escape"], 700),
    (["n"], 4500),  # 6. node reliability, with the --exclude line
]


# Named once so both import sites report the same remedy, and reported rather than
# raised: this file exists because a build step nobody can run does not happen, and
# a bare ModuleNotFoundError does not tell a contributor what to install.
_INSTALL_HINT = 'the GIF generator needs `pip install -e ".[assets]"` (%s is missing)'


def _rasterize(svg: str) -> bytes:
    try:
        import cairosvg
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit(_INSTALL_HINT % "cairosvg") from exc

    # The @font-face block points at a CDN. Dropping it stops cairosvg trying to
    # fetch a font it cannot reach and silently falling back to a proportional one.
    svg = re.sub(r"@font-face\s*\{[^}]*\}", "", svg)
    svg = svg.replace('font-family: "Fira Code"', 'font-family: "%s"' % MONO)
    svg = svg.replace("font-family: Fira Code, monospace", 'font-family: "%s", monospace' % MONO)
    return cairosvg.svg2png(bytestring=svg.encode(), output_width=PIXEL_WIDTH)


async def main() -> int:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit(_INSTALL_HINT % "pillow") from exc

    from slurmpast.demo import DEMO_SITE, history
    from slurmpast.site import reset_cache, site
    from slurmpast.tui import SlurmpastApp

    # Pin the synthetic cluster, as cli._load does under --demo: otherwise the
    # memory and GPU notes are worded from whatever cluster this runs on.
    reset_cache()
    site(runner=lambda _args: DEMO_SITE)

    jobs = history()
    frames, durations = [], []
    app = SlurmpastApp(lambda: list(jobs), window="synthetic demo data", no_logs=True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        for keys, hold in BEATS:
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.pause()
            frames.append(Image.open(io.BytesIO(_rasterize(app.export_screenshot()))))
            durations.append(hold)
            print("frame %2d  %-24s %5d ms" % (len(frames), "+".join(keys) or "(boot)", hold))

    out = ROOT / "assets" / "demo.gif"
    # Quantized per frame rather than once globally: the palette a dark terminal
    # needs is mostly greys, and a global 256 posterized the gauges.
    rgb = [f.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT) for f in frames]
    rgb[0].save(
        out,
        save_all=True,
        append_images=rgb[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(
        "\n%s  %d frames, %.1f s, %.0f KB"
        % (
            out.relative_to(ROOT),
            len(rgb),
            sum(durations) / 1000.0,
            out.stat().st_size / 1024.0,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
