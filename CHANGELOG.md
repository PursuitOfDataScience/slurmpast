# Changelog

All notable changes to slurmpast are documented here, newest first.

The format is based on [Keep a Changelog](https://keepachangelog.com), and this
project adheres to [Semantic Versioning](https://semver.org).

`issues.md` is the *audit* log — one entry per review round, including findings
that were withdrawn or deliberately left open. This file is the *release* log: what
changed for a user between one version and the next.

## [0.8.3] — 2026-09-09

Polish and bugfix work only — no API changes, so a patch release. Note that this
release is wider than the entries below: `_version.py` was already set to 0.8.3 by
the rounds thirty-eight to fifty-two commit, which was never tagged and never
reached PyPI (0.8.2 is the published version), so 0.8.3 ships those rounds too.
`issues.md` is the record for that earlier half — this file starts here. Every
entry below shipped with a regression test and a control verified in both states.

### Fixed

- **A dashboard signalled during startup reported that it had restored the terminal
  when it had not.** `_guard_startup_window` covers the gap before the app installs
  its own handlers, and it wrote the restore sequence through `sys.stdout` — but
  the window it covers opens the instant Textual emits the alternate-screen
  sequence, and Textual replaces `sys.stdout` and `sys.stderr` with capture
  objects at about that same moment. Their `write` queues into the app rather than
  reaching the terminal, and their `isatty()` still answers True, so the handler
  picked a capture, wrote the restore into it, and `os._exit` a microsecond later
  dropped the queue: the process exited **143 while the screen was still the dead
  dashboard**, which is the exact failure the guard exists to prevent, and the
  exit code made it look handled. Measured both ways — deterministic with a
  stand-in capture in place (restore missing 2 of 2), and **1 real pty run in 5**
  for the live dashboard, since whether the signal beats the redirect decides it.
  The restore now goes to the terminal's file descriptor, which cannot be
  redirected. `SIGTERM`/`SIGHUP` still exit 143/129 and the post-mount handlers
  are untouched.

- **Two of the three bar-drawing paths drew a solid bar well below 100%.** `bar`'s
  own documentation states the rule — "the last eighth is withheld until the
  percentage rounds to 100, so a visually full bar always means 100%" — and only
  its Unicode path applied it. The `--ascii` path and the `flat` path, which is
  what the **plain report** draws with, both round to whole cells and reserved
  nothing: measured at widths 8 and 18, **98.0% drew `########` under `--ascii`
  while the Unicode bar drew `███████░`** for the same figure, beside the same
  "98.0%" label. Every value from about 97% up disagreed between the paths. All
  three now reserve the final cell until the one-decimal label reads `100.0%`,
  which is the same test the low-end sliver rule already used — and the same
  disagreement that rule was written to fix, at the other end of the bar.

- **"Stop resubmitting; the failure is deterministic" was said to work that had been
  submitted once, and to work that had succeeded.** Every task of a job array is its
  own accounting record, and they fold into one workload — correctly, because each
  task really ran and burned resource. The *advice* assumed there had been that many
  submissions. Measured on a 30-day history: an eleven-task array with three
  COMPLETED tasks was told to stop resubmitting a deterministic failure, and so was
  a workload that had completed **50 of its 100 runs**. The action now says only
  what holds: an array is named as one submission and pointed at reproducing a
  single task, and a workload with any successful run is told the failure is *not*
  deterministic, with the count, and to compare a failed run against a completed
  one. The evidence line names the array (`All 11 are tasks of one array (job
  53410199)`). **No count, severity or exit code moves** — "8 of 11 runs failed" is
  unchanged, because those eleven allocations happened.

- **A confidence interval could print both of its ends as the same boundary.** The
  interval formatter built its own `%.1f` instead of asking the percentage
  formatter, so it kept the defect that one was fixed for: an interval of
  [99.96%, 100%] came out as `100.0 – 100.0%`, which says the measurement was
  exact when the lower end is a bound the data never reached. Each end now goes
  through the same formatter as every other percentage the tool prints, so that
  range reads `>99.9 – 100.0%`. Exact ends are unchanged — `0.0 – 100.0%` and
  `75.7 – 100.0%` are byte-identical — and only the strictly interior band moves.
  (This closes the item round fifty-six recorded as open in `issues.md`.)

  **The limit, measured, and left alone on purpose:** this fixes the two
  *boundaries*, not every tie. An interior interval narrower than the printed
  resolution still shows one figure twice — `format_rate_range(0.50001, 0.50009)`
  is `50.0 – 50.0%` and `(0.0006, 0.0009)` is `0.1 – 0.1%`, both unchanged. Those
  are the one decimal place every percentage in this tool carries, not a false
  claim: `100.0%` of a failure rate means *nothing succeeded* and `0.0%` means
  *nothing failed*, so printing one for an end that never reached it states a fact
  of a different kind, which a rounded `50.0%` does not. Closing the interior ties
  would mean widening every interval the tool prints to `%.2f` — the option round
  fifty-six weighed and declined — and would only move the tie one decimal along.
  The test module's docstring said the defect was "a range whose two ends print
  identically", which is wider than the change; it now says which two values are
  claims and pins the interior ties as a control.

- **Two tests for the interval fix could not have caught it.** Found by audit and
  replaced, with the fix neutered to confirm each replacement reddens.
  `test_the_dashboard_cell_agrees_with_the_helper` asserted
  `ci_range(x, y) == format_rate_range(x, y)`, and `render.ci_range` is literally
  `return format_rate_range(low, high)` — a tautology that held with the fix
  reverted and could not fail for any input. It is now driven through the real
  renderers on a real job set whose interval lands in the bounded band (8000
  failures on one node — `wilson_interval(8000, 8000)` is [99.952%, 100%], and
  7680 is the smallest table for which this package's statistics reach the band
  at all), and asserts that both `--plain`'s node table and the dashboard's
  `95% CI` cell print `>99.9 – 100.0%` — measured, both print `100.0 – 100.0%`
  with the fix reverted.
  `test_the_format_is_not_re_derived` read `duration.py` and asserted `"%.1f"` was
  absent from the function body, which pins the implementation and detects a
  reverted edit rather than a wrong string; it now asserts the property on output
  instead — each end of a range is byte-identical to the single-value formatter of
  that end, across all eight values that span the bands it distinguishes.

- **Two `--plain` notes went out at whatever length they happened to be.** The
  memory-footprint note is 109 characters on a real history (`40,994 rows parsed,
  about 40.0 MiB held — …`) and was printed unwrapped, so it hard-broke mid-sentence
  on every terminal measured — 60, 70, 80, 90 and 100 columns. The truncation
  summary below the workload table (`… 354 more workloads (8262 runs) holding 14.0%
  of the compute`) is 63 and overran the 60-column floor. Both now wrap to the
  terminal like the nine paragraphs around them, and the truncation summary keeps a
  hanging indent so a wrapped continuation does not read as another table row.

- **A `sinfo` query that failed was remembered as a measurement.** The per-partition
  hardware ceiling is what stops `--sizing` recommending more cores than a node has,
  and a failure correctly answers "unknown" — but the failure was also written into
  the cache, which is consulted before the query. So one transient failure (no
  `sinfo` on PATH yet, a timeout) disabled the clamp for the rest of the process.
  Measured: a first call with `sinfo` raising, then a second with a working `sinfo`
  returning `128 256000`, still answered "unknown" and never re-ran the query.
  A failed query is no longer cached; output that answered but would not parse still
  is, because that is a measurement about the partition.
- **Startup waited up to five minutes on the live-metrics query.** `sstat` contacts
  each job's step daemon, so its cost scales with how many jobs you have *running*,
  not with the window — measured at **119.76s for 60 running array tasks** — and it
  was bounded only by the 300-second accounting-database timeout. It now has its own
  15-second budget and falls back to reporting those fields as unmeasured, which is
  the documented answer. `$SLURMPAST_TIMEOUT` still caps it if lowered.
- **The dashboard and `--plain` disagreed about how to say a job has no node.** The
  plain report wrote `-`, the dashboard wrote nothing, so a pending or
  cancelled-before-allocation job showed a blank cell in one surface and a marker in
  the other. Eleven of the twelve job columns already agreed; this was the twelfth.

### Known issues

- **Quitting the dashboard can leave the process running for ~21 seconds** after the
  terminal is restored. The load runs on a thread that Python joins at exit and an
  in-flight parse cannot be interrupted. Before the live-metrics budget above it was
  unbounded — a process that never exited at all. See `issues.md` SP-2 for the
  measurement and the three candidate remedies; all three change process-exit or
  threading semantics and want a decision rather than a quiet patch.
