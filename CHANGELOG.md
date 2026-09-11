# Changelog

All notable changes to slurmpast are documented here, newest first.

The format is based on [Keep a Changelog](https://keepachangelog.com), and this
project adheres to [Semantic Versioning](https://semver.org).

`issues.md` is the *audit* log — one entry per review round, including findings
that were withdrawn or deliberately left open. This file is the *release* log: what
changed for a user between one version and the next.

## [Unreleased]

### Changed

Performance only. Nothing on screen moves, no flag changes meaning, and every
text surface (`--plain`, `--overview`, `--patterns`, `--nodes`, `--sizing`, and
each of their `--json` forms) was verified byte-identical to the previous release
over a fixed window before and after. Measured on midway3 (Slurm 20.11.8) against
one user's last seven days — **29,624 jobs, 89,163 sacct rows**:

| | before | after |
|---|---|---|
| `slurmpast --plain`, first run | 20.7 s | **5.5 s** |
| `slurmpast --plain`, every run after | 20.7 s | **2.1 s** |
| the sacct query inside it | 14.5 s | **3.1 s** |
| peak RSS | 250 MB | **137 MB** |
| `a`, the flat job list | 9.7 s frozen | **0.20 s** to a drawn screen |
| typing a word into that list's search | one rebuild per character | **one, when you stop** |
| `p`, the patterns panel | 0.51 s frozen | **0.01 s** |
| an arrow key, overview | 850–5400 ms | **17 ms** |
| an arrow key, inside a workload | 850–5400 ms | **6 ms** |
| an arrow key, flat job list, mid-fill | — | **5 ms** (was 110) |
| `assign_logs` over the history | 16.7 s | **1.2 s** |

- **A finished job's record is kept and reused.** A job that has ended cannot
  change, so re-reading 29,624 of them out of `sacct` on every run was the single
  largest thing left. Records now go to `$XDG_CACHE_HOME/slurmpast` (or
  `~/.cache/slurmpast`) — 18 MB for this history — and a second run inside the
  same window costs **2.1 s against 5.5 s**, with byte-identical output.

  What makes it safe is a fingerprint rather than a timestamp. Every run already
  asks sacct for the window's job list to partition the read; that listing now
  carries `State` and `End` too, and a stored record is reused **only when what
  sacct says about it right now is exactly what it said when the record was
  filed**. So a job still running is never stored at all; one requeued after it
  finished comes back with a different `(state, end)` sequence, because `-D` lists
  every incarnation, and misses; an edited state misses for the same reason; and
  an unexpanded pending array is not terminal, so it is never stored. The file is
  keyed by the package version and by the exact field list its records were parsed
  from, and a mismatched, truncated or unreadable one is treated as no cache
  rather than as something to salvage. A cache that cannot be written — full
  quota, read-only home — costs the reader nothing but the seconds they were
  already spending.

  `--no-cache` turns it off for one run and `SLURMPAST_NO_CACHE=1` for every run.
  An injected `runner=` never caches at all: canned text is not the cluster's
  accounting database, and filing one as the other is the only way this could hand
  back a job that never existed.

- **A window query is now read by several `sacct` processes at once.** Almost all
  of a window query's cost is `sacct` itself laying out rows, single-threaded:
  the same seven days cost 5.8 s at one field and 14.5 s at the eighty this tool
  asks for. The job ids are now fetched first with a cheap `-X --format=JobID`
  (0.41 s) and the full read is partitioned across them with `-j`. Splitting by
  *time* would not do: sacct filters step rows by the window too, so a job
  spanning a boundary comes back with only some of its steps and its `MaxRSS` is
  then read off a fragment. Every filter is passed to both halves, so the rows
  are the ones a single query would have returned — verified against the live
  scheduler: same 22,359 jobs, no id in one and not the other. Below 400 jobs the
  single query is still used, and a site that refuses either half falls back to
  it silently and stops trying. Ctrl-C still interrupts (the threads are daemon
  threads for exactly that reason).

- **The dashboard no longer freezes while it draws a long table.** Three causes,
  all in `tui.py`. Textual's `DataTable` measures every cell of every row to size
  columns that this app always gives an explicit width — 355,404 measurements and
  4.1 s per redraw of the flat list, for a number nothing reads; `FastDataTable`
  skips it while that stays true and falls back to stock behaviour if a row ever
  arrives with a label or an auto height. A job's rendered cells are now kept for
  the life of a loaded history rather than recomputed on every filter, search
  keystroke and resize. And the rows themselves are drawn a screenful at a time,
  the rest arriving between keystrokes — the table still ends up holding every
  row, so `end`, a digit jump and the scrollbar mean exactly what they meant.

- **Three repeated computations are now done once.** `Job._from_steps` — which
  `total_cpu`, `cpu_utilization` and `looks_like_noop` all come through, several
  times per job on every screen — builds no intermediate lists. `History.patterns`
  is warmed in a worker thread once the overview is up, so `p` no longer pays
  0.51 s on the keypress. `History.group_patterns` caches per workload, so the
  workload screen's summary stops re-deriving it on every keystroke. The two
  string parsers on the hot path (`parse_duration`, `parse_bytes` — 446k and 625k
  calls on one history) take their absent-value exit before building a string;
  122 inputs were compared against the previous behaviour with no difference.

- **`Sacct(parallel=False)`** turns the split off for a caller that wants the one
  query, and a resize that does not change the size no longer rebuilds a screen.

- **Moving the cursor in the dashboard took seconds, and log resolution was why.**
  The worst of it, and the one that made the dashboard feel broken rather than
  slow. `assign_logs` runs in a worker thread once the history lands, and on the
  same 29,617-job history it took **16.7 s** — during which every arrow key took
  between **0.85 s and 5.4 s** to redraw, while the same keypress under
  `--no-logs` took 5 ms. It is Python, so it holds the GIL, and there was simply
  too much of it: the directory list was re-derived once per job (6.8M
  `os.path.normpath` calls, 116,006 `os.getcwd` syscalls for the same fourteen
  strings), each of ~166 conventional filenames was built into a path and then
  split straight back apart to ask the directory listing about it (6.9M
  `os.path.join`, 4.9M `os.path.split`), and the "is this job's id in this
  filename" test compiled a regex built from the job id — a different pattern for
  every job, so 49,019 compilations through a 512-entry cache. None of that
  changes an answer. It is now **1.2 s**, and a keypress is **5–34 ms**. Verified
  by running the whole pass both ways over those 29,617 jobs against an 893-file
  tree: 19,666 matches, 229 of them inferred from timing, and every entry
  identical.

- **The search box re-filters when you stop typing, not on every character.**
  Rebuilding the flat job list is 100-311 ms at 29,617 jobs -- 139 ms of that is
  `DataTable.clear`, which is Textual's own and scales with the rows in the widget
  -- so typing an eight-letter query was eight of those back to back. One rebuild,
  150 ms after the last keystroke. Enter commits without waiting and escape
  cancels without waiting, and escape also CANCELS the pending rebuild rather
  than outrunning it, so a query you just abandoned cannot reappear a moment
  later.

- **`looks_like_noop` is remembered per job.** The job list asks it about every
  matching job twice over — once for the row's colour, once for the summary's
  count — on every filter change and every search keystroke, and it walks the
  job's steps each time. 110 ms of a profiled 478 ms keystroke on a 29,617-job
  list, for an answer that cannot change while a history is loaded.

- **The background row fill now loses to the keyboard.** Drawing 29,617 rows a
  screenful at a time keeps the flat job list from freezing, but the first
  version spent four fifths of the idle time doing it — so for the three seconds
  it ran, an arrow key took **110 ms, worst 350 ms** in a real pty. It now takes
  a third of the idle time and stands aside entirely for 150 ms after any
  keypress, which puts that same key at **5 ms**. Nothing waits on the fill:
  `end` and a digit jump call `ensure_all_rows`, so the only thing deferred is
  rows arriving below the fold while somebody is navigating.

- **The log worker hands the GIL back.** Even at 1.2 s, `assign_logs` running in
  a thread behind a live dashboard was still worth 180 ms spikes on an arrow key
  -- and once the cache brought the data on screen at 2.9 s instead of 7.5 s, the
  keypresses landed while it was still working rather than after it. It now calls
  a `pace` hook every 500 jobs, which the dashboard answers with a 1 ms sleep:
  59 pauses over a 29,617-job history, 59 ms of added wall clock on a background
  pass, and the arrow key is back to **5–13 ms**. `sleep(0)` is not enough --
  CPython treats it as a yield the same thread usually wins straight back. The
  hook defaults to `None`, so a library caller resolving logs in the foreground
  gets exactly the behaviour it always had.

- **Parsing is serialised across the query threads.** They query in parallel,
  which overlaps properly because that is subprocess time, but eight Python
  parses at once only take turns badly: 4.4–4.8 s unserialised against 4.0 s with
  a lock, and one parse's intermediates alive instead of eight.

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
