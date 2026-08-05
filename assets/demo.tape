# slurmpast demo — an ALTERNATIVE recorder, for real keystroke animation.
#
#   vhs assets/demo.tape            (overwrites assets/demo.gif)
#   Requires https://github.com/charmbracelet/vhs  (conda: vhs ttyd ffmpeg)
#
# The GIF actually committed to assets/ is built by `python tools/demo_gif.py`,
# which needs none of that toolchain — only what a dev install already brings in.
# That matters: this tape has never once been run to completion here, which is why
# assets/demo.gif did not exist for the first several releases while README pointed
# at it, and the repository's lead image 404'd.
#
# The two tell the same story and must be kept in step. If you change the beats in
# one, change them in the other. Two differences are deliberate, both fixes:
# after `f` the hung workload is row 2, not 3 (3 is a single-run workload), and the
# job screen is scrolled to its findings, which are below the fold at 30 rows.
#
# Drives the REAL slurmpast dashboard against `--demo`, a synthetic history
# built into the package (src/slurmpast/demo.py). That keeps the recording
# reproducible on any machine — no Slurm, no sacct, nothing queued — and the
# header reads "SYNTHETIC DEMO DATA" throughout so a frame from this GIF can
# never be mistaken for a real measurement.
#
# The synthetic history deliberately contains the shapes the tool exists to
# find: a workload that hangs and times out at an unchanged --time, a --mem
# hand-search that ends by succeeding at a value that already OOM'd, healthy
# training runs that correctly draw no findings, and one node that eats jobs.

Output assets/demo.gif

Set Shell bash
Set FontSize 16
Set Width 1400
Set Height 860
Set Padding 18
Set Framerate 24
Set Theme "Catppuccin Mocha"

Hide
Type `cd /tmp && clear`
Enter
Show

# --- 1. The overview: 58 jobs rolled into workloads, ranked by cost ---------
Type "slurmpast --demo"
Enter
Sleep 3s

# Walk down the ranked workloads so the outcome ribbons and IDLE column read.
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 1200ms

# --- 2. Filter to just the problems ----------------------------------------
Type "f"
Sleep 2s

# --- 3. Open the hung workload ---------------------------------------------
Type "3"
Sleep 700ms
Enter
Sleep 2500ms

# --- 4. Into one job: the full post-mortem, every field, with gauges --------
Enter
Sleep 4s

# Back out to the workload, then to the overview.
Escape
Sleep 900ms
Escape
Sleep 900ms

# --- 5. Cross-run patterns: the repeat failure and the memory hand-search ---
Type "p"
Sleep 4500ms
Escape
Sleep 700ms

# --- 6. Node reliability, workload-controlled, with the --exclude line -----
Type "n"
Sleep 4s

Escape
Sleep 600ms
Type "q"
Sleep 1s
