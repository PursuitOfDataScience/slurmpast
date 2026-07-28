"""Shared visual vocabulary, deliberately identical to slurmwatch's.

The two tools sit either side of the same job -- slurmwatch while it runs, this
one after it stops -- so a colour must mean the same thing in both. Amber is
"warning" in one and "warning" in the other; the CPU row is the same cyan on
both screens. These constants are copied rather than imported because slurmpast
must install and run on a machine that has never seen slurmwatch.
"""

from __future__ import annotations

# Text planes (warm, so the palette does not read as a cold default terminal).
INK = "#ede7dd"  # primary text (warm off-white)
DIM = "#b3a998"  # secondary text
FAINT = "#857d70"  # faint text / empty bar track
ACCENT = "#d97757"  # coral — the one chrome accent

# Per-resource identity hues, spread across the wheel so no two read alike even
# on a 256-colour terminal or with red-green colour blindness.
CPU_COLOR = "#159fc0"  # deep cyan
MEM_COLOR = "#df5f97"  # rose
GPU_COLOR = "#8a6ee6"  # violet
DISK_COLOR = "#2f9e8f"  # teal

# One health vocabulary everywhere: green fine, amber warning, red critical.
HEALTH_COLOR = {
    "ok": "#6aa84f",
    "warn": "#e2bb4c",
    "crit": "#d1584f",
    "none": FAINT,
}
HEALTH_GLYPH = {"ok": "●", "warn": "●", "crit": "●", "none": "·"}
HEALTH_GLYPH_ASCII = {"ok": "+", "warn": "!", "crit": "x", "none": "-"}

# Terminal state -> health grade. CANCELLED is deliberately "none", not "crit":
# a deliberate kill and an abandoned run are indistinguishable in accounting, so
# colouring it red asserts a judgement the data does not support.
STATE_HEALTH = {
    "COMPLETED": "ok",
    "FAILED": "crit",
    "TIMEOUT": "crit",
    "OUT_OF_MEMORY": "crit",
    "NODE_FAIL": "crit",
    "BOOT_FAIL": "crit",
    "DEADLINE": "crit",
    "CANCELLED": "none",
    "RUNNING": "warn",
    "PENDING": "none",
}

SEVERITY_HEALTH = {"critical": "crit", "warning": "warn", "info": "none"}

BAR_WIDTH = 18


def theme() -> object:
    """The Textual theme, registered under our own name.

    Imported lazily so the analysis modules stay usable without Textual
    installed -- `--json` on a login node should not need a UI framework.
    """
    from textual.theme import Theme

    return Theme(
        name="slurmpast",
        primary=ACCENT,
        secondary=MEM_COLOR,
        accent=GPU_COLOR,
        foreground=INK,
        background="#141312",
        surface="#1e1c1b",
        panel="#262320",
        success=HEALTH_COLOR["ok"],
        warning=HEALTH_COLOR["warn"],
        error=HEALTH_COLOR["crit"],
        dark=True,
    )
