# slurmpast — audit and resolution

> **Round six, 2026-08-05, from `4f12dc1`.** Filed as issue #5. Round five's ten
> defects, its documentation set and all six of its minor items re-verified as
> genuinely fixed — by running each reproduction again, not by reading the entries
> below. Seven new: one false claim about a live job, introduced *by* one of round
> five's own fixes, and six unwrapped prose lines, which are one defect wearing six
> hats. 1166 tests before, **1195 after**.
>
> Stated plainly, because the round itself could not run the full gate: the audit
> environment had no network, so `pytest`, `rich` and `textual` could not be
> installed. The suite was executed against a stubbed `rich.text.Text` through a
> pytest shim (905 of the items, everything not requiring Textual, 0 failures), the
> new count was computed from the collection rules, and `ruff`, `ruff format` and
> `mypy` were not claimed.
>
> **All four gates were then run for real at review, on the full suite including
> the three Textual modules: 1195 pass, `ruff`, `ruff format` and `mypy` clean.**
> The predicted count was exact. Review added one fix of its own, below.
>
> **Round five, 2026-08-05, from `f505d44`.** A full read of all 19 modules,
> filed as issue #1. Ten defects plus the documentation set, every one reproduced by
> running the code before it was written down, and two candidates withdrawn on
> re-verification and said so. All ten fixed here, along with every minor item and
> the **Open** gauge entry below, which a second reviewer has now raised. 1,098
> tests before, **1166 after**. `ruff`, `ruff format` and `mypy` clean.
>
> **Round four, 2026-08-03, from `4d47d4d`.** Not a sweep — two defects, both
> surfaced by one user question ("does slurmpast support me looking at other users'
> past jobs?"). The answer was yes, and asking it found that the multi-user path
> was half-built: a `--allusers` branch nothing could reach, and a `user` argument
> that every modern Slurm ignored. 1,083 tests before, **1,098 after**. `ruff`,
> `ruff format` and `mypy` clean.
>
> **Round three, 2026-07-31, from `7f32b1a`.** Thirteen defects found, thirteen
> upheld by a three-reviewer panel, thirteen fixed, plus one the panel found that
> was not on the list. 1,029 tests before, **1,083 after** — 54 new, one per fix
> and its control. `ruff`, `ruff format` and `mypy` clean.

---

## Round six — issue #5

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A queued array element was reported as "long gone" | `sacct.live_job_ids` | `TestSqueuePrintsPendingArraysAsRanges` (`test_sacct.py`) |
| 2 | Both node-screen "nothing to say" sentences overran *every* width | `render.nodes_empty_reason` | `TestEverySentenceWrapsIncludingTheEmptyOnes` (`test_layout.py`) |
| 3 | The job screen's `log` line overran every width | `report.render_job` | `test_only_the_recorded_log_path_may_overrun` |
| 4 | The node screen's `baseline` line, the third unwrapped sibling | `render.nodes_baseline` | `test_the_baseline_line_wraps` |
| 5 | `--sizing`'s group header carried an unbounded name and partition | `report.render_sizing` | `test_the_sizing_screen_wraps_its_headers_and_its_empty_line` |
| 6 | `--sizing`'s "nothing to advise" line was 66 cells | `report.render_sizing` | *(same)* |
| 7 | The documented node-table floor was wrong, and it hid #4 | `render.table_floor` | `test_the_documented_node_table_floor_is_the_one_the_spec_gives` |
| 8 | Sharing a sentence averaged away the one clause that differs per surface | `render.nodes_empty_reason` | `TestASharedSentenceKeepsWhatIsSurfaceSpecific` (`test_layout.py`) |

**Six of the seven are one defect.** Round five wrapped the prose lines its own
reproductions happened to reach and left the siblings beside them — in
`render_nodes` it wrapped the `controlled for workload` line and the `UNCONTROLLED`
warning, and left the three lines under them. That is the shape this file has now
named three times: round three's "#21 corrected the *caption* above the workload
table and left the *footer* below it wrong", round five's #6 and #7, and now this.
The pattern is not carelessness about lines, it is scope taken from whatever the
reproduction touched, so the fix here is structural: the sentences both screens draw
moved into `render`, where a wrap applies once.

### 1. squeue does not print one id per pending array task

It prints the range. `900_[5-10]` — the same bracketed grammar Slurm uses for
hostlists, which `nodes.expand_nodelist` has parsed since round one and is
differential-tested against `scontrol show hostnames`. `cli._mark_open_records`
tested membership against the raw set, so every *pending* element missed.

Round five is what made that a defect rather than a wasted call. Before it the set
was fetched and discarded, so nothing was claimed; the fix turned the value into a
user-facing assertion without teaching it the range spelling, and the miss became
the strongest of the finding's three sentences:

```
squeue --format=%i returns: '900_[5-10]'

  900_7   PENDING  live=False
      -> squeue has never heard of it, so the job is long gone and the record was
         never closed. The elapsed above is an artefact.
```

The job is queued at that moment. A `PENDING` record reaches the path because
`open_ended` is `not end_raw and state not in _TERMINAL_STATES`, and `PENDING` is in
neither set. Expanded in `sacct.live_job_ids`, so every caller gets individual ids
rather than each one learning the grammar.

The `%N` throttle is stripped first. `--array=0-9%2` comes back *inside* the
brackets as `900_[0-9%2]`, and left in place it defeats the expansion silently:
`0-9%2` is not a numeric range, so the parser keeps it verbatim as one unmatched
name and every element of a throttled array goes on being called dead. Unknown
spellings still match themselves, so failing to understand one costs exactly what
the whole set cost before.

### 2, 3, 4, 5, 6. Five sentences, measured

```
                                                  before   after
nodes, "No hangs recorded for <workload> ..."        132      wraps   (every width)
nodes, "No node reached the N placements ..."        122      wraps   (every width)
job,   "log <path>  (matched by timing ...)"         133      wraps   (every width)
job,   "log none at <path> — moved or deleted"       122      wraps   (every width)
sizing, "<workload>  <partition> · N runs"            86      wraps   (at 80)
nodes, "baseline N% over M placements; ..."            67      wraps   (below 68)
sizing, "every workload is already about right"        66      wraps   (below 66)
```

Four of those overran **every** terminal width, not merely narrow ones, and three of
them are the line a view falls back to when it has nothing else to show — so the
sentence round three added to rescue an empty screen ("printing a column header over
no rows … is what made this screen read as useless") was the longest thing on it.
Two carry a folded workload name, which is round five's #6 in branches that round's
reproductions never entered: `cot-exp` in the demo,
`nemotron-batch-h#-tokenize-shards-stage#-retry-#` on a real cluster.

**One overrun is kept, and named.** A recorded log path is never shortened —
`--plain` exists to be pasted and `wrap` cannot break a token with no spaces in it —
so a path wider than the terminal still overruns. What did not have to was the 58
cells of prose riding beside it. Where the pair fits, the line is byte-identical to
before; the same applies to the sizing header, whose two-space separator `wrap`
would otherwise have collapsed.

### 7. A number taken from a screenshot

`render.table_floor(NODE_COLUMNS)` returns **41**. Three places said 67:
`table_floor`'s own docstring, the `PLAIN_MIN_WIDTH` comment, and round five §6&7
above. 74 for `JOB_COLUMNS` was right.

67 is not a table floor at all. It is the length of the unwrapped `baseline` line in
#4 — measured off the rendered view and written down as a property of the column
spec. That is worth recording rather than quietly correcting, because it is the one
framing under which a wrappable sentence never gets wrapped: filed as a column-spec
property it is an unavoidable limitation, and #4 sat behind it for a round.
`test_the_documented_node_table_floor_is_the_one_the_spec_gives` now asserts the
relationship rather than the number, so a new never-dropped column moves it.

### 8. Added at review: a shared sentence kept its keystroke

Pooling the two empty-table sentences into `render` was the right call — it is what
`render.py` is for, and it settled a real drift where `report` said "below threshold"
and `tui` said "below sample threshold". But it also averaged away the one clause
that is *supposed* to differ. The plain report had told the reader

    A wider --since window is what fixes this.

and the dashboard had told them `(w)`. The shared version said neither:

    A wider window is what fixes this.

That is the only actionable clause in the sentence, and dropping it is the same
defect `format_duration`'s `HH:MM:SS` and `format_mem_flag`'s `52G` exist to prevent
— name the thing the reader actually types. `nodes_empty_reason` now takes `widen`,
so the wording stays shared and the keystroke is passed in.

Worth recording as its own item rather than folded into #2, because it is a hazard
of the *remedy* rather than of the original defect, and the remedy is one this
codebase reaches for often: consolidating a duplicated string is not free, and what
it costs is exactly the part that was different on purpose. Nothing caught it — the
suite was green at 1,190 with the clause gone.

### Confirmed fixed from round five

Every reproduction re-run: 30 explicit ids give 30 post-mortems and 30 JSON entries;
`sigkill` fires on `FAILED` alone; the memory-slack action reads `--mem=52G`; the
injected runner gets the `--helpformat` probe and nothing escapes to the module
`_run`; `--no-logs` emits no log line at all; a folded workload name fits 80, 100
and 120; the job detail fits from 60 up; `_elide` honours `keep` in all three shapes;
the demo's clock agrees with its ids and `--sizing` reads `(from 32.0 GiB)`; `r`
snapshots `_previous`. The demo contains its advertised bad node —
`--demo --nodes` names `midway3-0385` at 12/12 with a paste-ready `--exclude`. All
six minor items hold.

### Consequence for the numbers

None. Every change is presentation, except #1, which changes one sentence on an
open record from a false claim to a true one and leaves `open_ended` — and so every
aggregate — exactly as it was.

---

## Round five — issue #1

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | Explicit job ids silently truncated at `-n`, so a CRITICAL past the limit could not reach the exit code | `cli.main` | `TestExplicitIdsAreNotTruncated` (`test_cli.py`) |
| 2 | The SIGKILL finding fired CRITICAL on five states that already explain the kill | `diagnose._exit_rules` | `TestSigkillOnlyFiresWhenNothingElseExplainsIt` (`test_diagnose.py`) |
| 3 | `--mem=52.0 GiB`, a flag `sbatch` rejects | `diagnose._memory_rules` | `TestAdviceIsPasteable` (`test_diagnose.py`) |
| 4 | `Sacct(runner=...)` probed the *local* sacct for its field list | `sacct.supported_fields` | `TestAnInjectedRunnerIsUsedForTheProbeToo` (`test_sacct.py`) |
| 5 | Under `--no-logs` the report asserted a filesystem fact it never checked | `report.render_job` | `TestNoLogsClaimsNothingAboutTheFilesystem` (`test_cli.py`) |
| 6 | The nodes workload line was never wrapped | `report.render_nodes`, `tui.NodesScreen` | `TestPlainOutputFitsATerminal` (`test_layout.py`) |
| 7 | The job detail overran *any* terminal, and the width tests never went below 80 | `render.resource_rows`, `report` | `test_no_job_detail_line_overruns_the_terminal` (`test_layout.py`) |
| 8 | `_elide` mangled any value containing `/`, and ignored its own budget | `tui.JobScreen`, `tui._elide` | `TestOnlyPathsAreElidedLikePaths` (`test_tui.py`) |
| 9 | `--demo` timestamps wrapped every ninth job, reversing the narrative and feeding `_latest` a wrong "last run" | `demo._job` | `TestTheDemosClockAgreesWithItsJobIds` (`test_cli.py`) |
| 10 | `r` exited the app on a transient query failure, with the history already discarded | `tui.SlurmpastApp.action_reload` | `TestReloadSurvivesATransientFailure` (`test_tui.py`) |

### 1. `--limit` stops applying to ids the caller typed

`targets = matches[: args.limit]` ran on the job-id branch too. `-n` defaults to 25
and is documented as "rows in plain output", so `slurmpast <30 ids>` printed 25
post-mortems and said nothing about the other five; `--json` returned a 25-entry
array for a 30-id query. Every other truncation here names its tail
(`History.tail_summary`, `nodes.excluded_tail`, `render_list`'s "… N more"); on this
branch no renderer ever does, because a post-mortem block has nowhere to put such a
line.

The exit code is what made it more than a display bug: it is computed only over the
jobs examined, so 26 healthy ids followed by an `OUT_OF_MEMORY` exited 0.

### 2. SIGKILL says something only when nothing else does

Slurm reaches for signal 9 on `CANCELLED`, `TIMEOUT`, `PREEMPTED`, `NODE_FAIL` and
`OUT_OF_MEMORY` alike, once `KillWait` expires. Each already produces a finding
naming its own killer, so the rule added a second one whose action — "look for a
wrapper or watchdog killing it" — sent the reader after a phantom, directly beneath
the tool's own sentence saying what actually happened.

Severity was the other half. `theme.STATE_HEALTH` grades CANCELLED `"none"` because
"colouring it red asserts a judgement the data does not support" — and a CRITICAL
here asserted it anyway, through the exit code: `slurmpast <jobid>` returned 1 on a
run the tool had just called not a failure. Suppressed by state, the same shape and
for the same reason as `_NOOP_ALREADY_EXPLAINED` two rounds earlier. `test_sigkill`
covered `state="FAILED"` only, which is the one state where nothing else explains
it — so the rule read as working.

### 3. A flag you can paste

New `duration.format_mem_flag`: bytes to the whole-GiB spelling `--mem=` accepts,
rounded up, beside `format_duration`'s `HH:MM:SS` and closing the same defect its
docstring describes. `sizing.memory_advice` had the right spelling all along, so the
tool's two sizing surfaces disagreed about one flag.

### 4. The probe goes where the queries go

`supported_fields` called the module-level `_run` unconditionally, so a caller
replaying a recorded history or reaching a remote cluster negotiated its field list
against whatever sacct was on the local `PATH`:

```
calls to the INJECTED runner : [['sacct', '--parsable2', ... , '-u', 'alice', ...]]
calls that escaped to _run   : [['sacct', '--helpformat']]
```

Trap 1 at the top of that module is why it is not a degraded answer but no answer:
one unknown field makes sacct reject the entire query. `_mark_open_records` makes
exactly this argument for `live_job_ids`; the hole was open one level up.

### 5. Nothing was stat'd, so nothing is claimed

`render_job` printed the "no log found" line unconditionally, and `--demo` forces
`no_logs`, so every synthetic post-mortem reported a search that never ran. With a
recorded `StdOut` the invented claim got stronger and was simply false — "none at
/scratch/dana/logs/sft-884411.out — moved or deleted" about a file nobody looked
for. `tui.JobScreen` has guarded the identical line all along.

### 6 & 7. Width, measured below 80 for the first time

The nodes workload line was a bare format string carrying a folded workload name:
`cot-exp` in the demo, `nemotron-batch-h#-tokenize-shards-stage#-retry-#` on a real
cluster, which took it to 114 cells on a 100-column terminal. Same shape as round
three's node table, which survived two audits because the demo's node names are 12
characters — so the long-name fixture now folds the workload name too.

The job detail was worse than reported: it overran **every** width, not merely
narrow ones, because three of its lines were fixed-length. It was never in the
width test's fixture at all.

```
                    before   after (COLUMNS=80)
gauge row + detail      86       80   detail moves to its own indented line
single-pair value       86       80   wraps, hanging under the value column
finding title           70       80   wrapped, like the evidence and action below it
```

The gauge fix is the **Open** item below, and deliberately not the width-adaptive
bar that entry declined: the row up to the value column stays a fixed 42 cells, so a
60% bar still looks the same here as in slurmwatch's live view, and at 100 columns
and up the output is byte-identical. Only the trailing `· detail` answers to the
terminal.

What cannot be fixed is named rather than clamped: a table with no droppable column
left has a floor, and `report.PLAIN_MIN_WIDTH = 60` was promising below it. New
`render.table_floor(spec)` computes it from the spec — 74 for the job list, 67 for
the node table — and the width test now runs at 60, 66 and 74 and holds each view to
its own floor, so adding a never-dropped column moves the bar instead of quietly
making the promise false.

### 8. A `/` is not a path

The dashboard elided any value containing one, which is true of `submitted as`
(SubmitLine, Slurm 21.08+) — a command line, not a path:

```
before  sbatch --job-name=midtrain ... --output=/scratch/midway3/youzhi/logs/%x-%j.out train.sh
after   sbatch --job-name=midtrain ... --output=/…/%x-%j.out train.sh
```

The one row recording where the output went lost its directory. Path-ness is now
declared by `render.PATH_ROWS` beside the rows themselves rather than sniffed at the
point of use; everything else is cut at the end, where the head carries the meaning.
And `keep` is a budget rather than a trigger: the middle-out form is tried first
because it is the readable one, but at `keep=30` it could still return 122
characters, and a shortening that soft-wraps anyway has bought nothing.

### 9. A clock that agrees with the job ids

```python
stamp = "2026-07-%02dT0%d:00:00" % (min(day, 28), jid % 9)
```

The hour wrapped every ninth job. All ten `rc-tok-github_code` runs carry `day=20`,
so they listed 08:00, 07:00, 06:00, 05:00, 05:00 — the narrative backwards, with two
runs sharing a timestamp. Slurm hands out ids in submission order, so this was a
demo of something Slurm cannot produce.

It fed a wrong number as well as a wrong order: `sizing._latest` picked 5100038
(17G) as the last submission instead of 5100044 (32G), and the sizing screen advised
`--mem raise to 42G (from 17.0 GiB)`. That is the error `_latest` was introduced to
fix in round two, arriving through the demo's own fabricated timestamps — and
`test_memory_requested_is_the_last_ceiling_not_the_largest` was **pinned to the wrong
value**, so the test proving `_latest` picks the last request would have gone on
passing had `_latest` broken.

**And the demo now contains the bad node it advertises.** `demo.tape` sells the
synthetic history as holding "one node that eats jobs", but the hang was spread
evenly across two (12/13 against 6/7), so with the workload held fixed — the only
comparison `--nodes` makes — `slurmpast --demo --nodes` answered *"no node is worse
than the rest; nothing to exclude"*, on the screen README leads its "Failure, across
runs" section with. It is now 12/12 on `midway3-0385` against 2/8 elsewhere, and the
screen names it with a paste-ready `--exclude`. The workload still hangs, so the
other advertised shapes are unchanged; all four are pinned by
`TestTheDemoContainsTheShapesItAdvertises`.

### 10. `r` fails the way `w` does

`action_cycle_window` snapshots `_previous` before re-querying and `action_reload`
did not, while `_requery` clears the history first and a successful load clears
`_previous`. So after any normal session `r` plus a slurmdbd blip tore the dashboard
down with the data already discarded, where the identical failure on `w` degraded to
a toast. `_loaded`'s own comment gives the reason: "Backing out beats exiting: they
still have the data they had." `_restore` now words itself for whichever key called
it — "nothing found there" is the wrong sentence for a reload, since there is no
"there".

### The documentation

**Every shipped screenshot predated several rounds of fixes, and each advertised a
bug the code had since closed** — a `KERNEL 192.7%` gauge (the impossible ratio
`system_cpu_fraction` now returns `None` for and names in its own comment), the
mixed-unit `USED` column `OVERVIEW_COLUMNS` documents at length as removed, the
invented `30m26s` format `format_duration` replaced, round three's `1 nodes below
sample threshold` pluralisation bug. README's pitch is that this tool prints `n/a`
rather than a fabricated number, illustrated by a screenshot of a fabricated number.

All five regenerated, and the reason they went stale — nothing could regenerate
them — closed with `tools/screenshots.py`, which drives the real dashboard headless
against `--demo` at the 100x30 the replaced assets were taken at. The test badge
moves from a two-round-stale 1029.

### Minor

* `_mark_open_records` **uses** the ids squeue returns instead of testing the answer
  for `None` and discarding it, so the reconciliation its docstring describes is
  performed rather than merely described. New `Job.live` — three-valued, because
  "squeue could not be reached" and "squeue has never heard of it" are different
  claims and only one is a measurement — and the open-record finding says which,
  rather than telling every reader to "confirm against squeue" about a query the
  tool had already run.
* `--all-users <jobid>` forwards `all_users` to the reconciliation, so someone
  else's live job is no longer checked against `squeue --me` and called stale.
* The hung-timeout caution no longer says "**further** timeouts … left out of **that
  floor**" where no preceding sentence established a floor (below `VETO_MIN_COUNT`,
  hangs with no computing timeouts).
* `"core" if peak < 2` printed "1.5 core busy per task" across the whole 1.0–1.9
  range; singular is now exactly one, and the denominator pluralises too.
* `site.site`'s two `refresh` branches were two spellings of one statement.
* `system_cpu_fraction`'s docstring described the pre-round-three step resolution.

### Withdrawn by the issue, and confirmed withdrawn

Two of the twelve candidates did not survive re-verification and the issue said so:
a suspected node-table width bug that was the same unwrapped prose line as #6, and
"the demo has no bad node", which was narrowed to "not under the workload control" —
and is what §9 above then fixed properly.

---

## Round four — the multi-user path

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `--allusers` existed but nothing could reach it, and no flag offered it | `cli._load` / `cli.build_parser` | `TestWhoTheQueryIsAbout` (`test_cli.py`) |
| 2 | `live_job_ids` ignored its `user` argument on every Slurm since 20.02 | `sacct.live_job_ids` | `TestSqueueReconciliation` (`test_portability.py`) |

### 1. `--all-users` reaches the branch that was already written

`Sacct.history` had `elif user == "": extra += ["--allusers"]`. `_load` then scoped
the query with `args.user or getpass.getuser()`, so the empty-string sentinel became
your own name before it ever arrived: `-u ""` reported **your** jobs while reading as
a request for everyone's. There was no flag for it either — while `patterns.group_key`
carried the user in the key specifically because "`--allusers` spans the cluster, so a
multi-user query is one flag away". The flag did not exist.

`--all-users` now exists and routes to that branch; `--all-users` together with `-u`
exits 2 rather than letting one win silently and scoping the output to something the
reader did not ask for. Verified on Midway3: 80,027 jobs across 1,612 workloads in a
two-day window, against 1,730 in 100 workloads for a single other account.

The empty-string spelling still works, since 0.4.0 shipped it as public API.

### 2. `--me` is only asked about me

`live_job_ids` tried `squeue --me` first **unconditionally** and fell back to
`-u <who>` only when that raised. `--me` has been in Slurm since 20.02, so on every
release anyone runs, the fallback never fired and the `user` argument was dead code:
`-u alice` reconciled alice's RUNNING records against *my* queue.

It read as working because the only test covered the fallback — it stubbed a runner
that **raises on `--me`**, which is the one condition under which the argument was
honoured. The `--me` attempt is now made only when the account being reconciled is
the caller's own; `--all-users` asks an unfiltered `squeue` on purpose, which is the
same command the docstring warns about as an accident.

Contained rather than harmless today: `_mark_open_records` only tests the result for
`None`, so a wrong-account answer changed no output. It was one caller away from
mattering, and three new tests pin each branch.

### Consequence for the numbers

None for a single-user query, which is the default and what every previous round
measured. `--all-users` is new surface: `patterns.group_key` already carried the
owner, so cross-account queries group per user rather than fabricating one shared
workload out of two people's `run.sh`.

---

# Round three — everything below this line

## Rounds one and two — verified closed before anything new was looked for

Every fix from the first two rounds is present at the site issues.md named for
it, checked by reading the code rather than by trusting the entry:

`nodes.node_p_value` / `_bh_reject` (1) · `sizing._latest` (2) ·
`sizing._memory_verdict` (5) · `model.Job.failed` carrying DEADLINE (6) ·
`model._tres_bytes(zero_is_missing=)` (7) · `index._SORT_KEYS["failures"]` on
`problems` (8) · `index.build_groups` materialising its input (9) ·
`diagnose._NOOP_ALREADY_EXPLAINED` (10) · `logs.Scan.exists` confirming a hit
(11) · `logs.expand_pattern`'s `own_id` (12) · `logs.job_identifiers`' array
master (13) · `patterns.group_key` carrying the user (14) ·
`patterns.find_memory_search`'s forward walk (15) · `sacct._FREE_TEXT` (16) ·
the hang veto's computing/hung split (17) · `sizing.cpu_advice`'s `busiest`
(18) · `cli.main` handing `render_list` the whole list (19) ·
`--overview --json` through `sort_groups` (20) · `render_overview`'s ordering
claim (21) · `--json`'s exit code (22) · `cli._glue_negative_values` (23) ·
`--demo --failed` (24) · `nodes` folding names before it strata (25) ·
`nodes.excluded_tail` (26) · `tui._load`'s guard around `History` (27).

Items 3 and 4 were decided "not a defect" and "by design"; both are unchanged
and both still read correctly. Nothing from those rounds regressed.

**Two of them turn out to have been fixed only on one side**, which is the
strongest pattern in this round. #21 corrected the *caption* above the workload
table for `--sort` and left the *footer* below it wrong (new #2). #24 fixed
`--demo --failed` and left `--demo -p` / `--demo -u` in the same state for the
same stated reason (new #8). Round two named this shape itself — "#5 is
issues.md #2 in the one branch that fix did not reach" — and it recurred twice.

---

## Method

Every module read in full, including `render.py`, which neither previous round
finished. Thirteen candidates were raised and each was reproduced by running the
code before being written down. All thirteen then went to **three independent
reviewers**, working from the running code, told to default to NOT-A-DEFECT on
thin evidence and to weigh the codebase's own documented intent.

**The panel returned 13/13 DEFECT, unanimous.** No candidate drew a 1-of-3 split,
so no second round of evaluation was needed. That is a weaker result for the
procedure than round two's (which rejected 7 of 23) and it is worth saying why
rather than claiming a clean sweep: this round's candidates were all reproduced
end-to-end before being listed, where round two's were raised from reading. The
panel's value here was in the **corrections** it made, not the rejections —

* **#5 was overstated.** Textual soft-wraps, so nothing clipped. The real harm is
  an inert width argument and a hanging indent lost on continuation lines. Two of
  three reviewers flagged this independently, and one warned the naive fix
  (dropping the `join`, keeping the `100`) would have introduced #10 there.
* **#11 was understated.** `read_bytes` also iterates `self.steps` rather than
  `work_steps`, so `.extern` pollution — the artefact `_from_steps` documents and
  excludes — reaches the I/O figures. Two of three reproduced it; a job whose
  extern step claimed 500 GiB against 1 GiB of real work reported 500. Fixed with
  #11, since it survives the `max`→`sum` change.
* **#6's worst case is worse than described.** At a 12-cell column
  `midway3-0600,midway3-0611` truncates to `midway3-0600` — not a visibly broken
  string but a **complete, valid, real node name** for a job that ran on two.
* **#9's payoff is smaller than claimed.** 2.2–5.9× on the function, ~4% of the
  whole log pass end-to-end, and unmeasurable on a small log directory.

One reviewer also found a **test-coverage gap** that let #4 survive two audits;
it is fixed below. All three confirmed the repo was untouched during review.

---

## Fixed

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A hung run's `--time` became the walltime floor for the whole workload | `sizing.walltime_advice` | `TestAHungRunIsNotEvidenceOfNeedingMoreTime` |
| 2 | "… N more workloads" described the cost-ranked tail whatever `--sort` said | `index.tail_summary` | `TestTheTruncationNoteDescribesWhatWasTruncated` |
| 3 | `--demo` attached real log files off the local disk to synthetic jobs | `cli.main` | `TestTheDemoStaysSynthetic` |
| 4 | The plain node table hardcoded its widths and ignored the shared spec | `report.render_nodes` | `TestTheNodeTableGoesThroughTheSharedSpec` |
| 5 | `" ".join(wrap(...))` made the workload banner's wrap a no-op | `tui.WorkloadScreen` | `TestTheWorkloadBannerWrapsAtAll` |
| 6 | A truncated node list read as a shorter, real, wrong node | `render.text_table` | `TestTruncationSaysSoInATable` |
| 7 | `--sizing` accepted `--sort` and discarded it | `cli.main` / `report.render_sizing` | `TestSizingHonoursTheSort` |
| 8 | `--demo` ignored `-p` and `-u` | `cli._load` | `TestTheDemoHonoursEveryNarrowingFlag` |
| 9 | The log scan rebuilt a membership set on every probe | `logs.Scan.exists` | `TestTheListingIsIndexedOnceNotPerProbe` |
| 10 | Dashboard findings wrapped to a fixed 86 cells | `tui.JobScreen` / `PatternsScreen` | `TestTheDashboardWrapsToTheTerminalItIsOn` |
| 11 | Disk I/O took the max across steps where CPU sums — and read `.extern` | `model.Job.read_bytes` / `write_bytes` | `TestDiskTotalsSumTheStepsThatMovedTheData` |
| 12 | `--sort recent` broke ties Z→A while every other sort broke them A→Z | `index.sort_groups` | `TestSortTieBreaksRunTheSameWayInEveryMode` |
| 13 | "1 nodes below threshold omitted" | `report` / `tui` | `TestCountsAreSpelledForTheirNumber` |
| — | A layout test built five views and asserted over two, exempting #4 | `tests/test_layout.py` | *(the test itself)* |

### 1. The walltime floor now comes from the timeouts that computed

`floor = max(...)` ran over every TIMEOUT. `hangs_dominate` needs three hangs AND
half the timeouts AND a fifth of the workload, so a *minority* of hangs never
reached the veto and set the floor unopposed — breaking rule 2 of the module's own
header, with the split it needed already computed fifty lines above.

`computing = [j for j in timeouts if not looks_like_noop(j)]` is now hoisted to the
top of the function and used by both the veto and the floor. Reproduced before and
after, on ten completed runs of an hour, six real timeouts at a 2-hour limit, and
two hung runs carrying a stale 24-hour one:

```
before  raise to 1-06:00:00   basis: longest of 10 completed runs took 01:00:00.
after   raise to 02:30:00     basis: longest of 10 completed runs took 01:00:00.
```

A 12× over-request, gone, and the basis and the number now agree. The caution was
counting the same set: it said "8 runs timed out, so the requirement is at least
the limit that cut them off" of two runs that provably never computed. It now reads
"6 runs timed out while computing … 2 further timeouts consumed almost no CPU and
are left out of that floor". The existing test pinning `max()` for the floor
(`test_a_timeout_floor_is_still_taken_from_the_largest`) uses a computing timeout
and is untouched, which is the control that matters.

### 2. The truncation note is told which list was sliced

`tail_summary(shown, ordered=None)` now takes the ordered list the caller actually
cut, instead of slicing `self.groups` behind its back. Measured on the demo at
`-n 3`:

```
             before                          after
--sort cost  23 runs / 10.9%   (correct)     23 runs / 10.9%
--sort name  23 runs / 10.9%                 30 runs / 86.4%
--sort rate  23 runs / 10.9%                 27 runs / 88.6%
```

The 86.4% and 88.6% were independently computed by two reviewers before the fix and
match. The old line told a reader that the hidden bulk of their history was a
negligible remainder — worse than silent truncation, which is the one thing this
line exists to prevent.

### 3. `--demo` no longer touches the filesystem for logs

A synthetic job wrote no log, so anything a search turns up is a real file
belonging to a real run — and its text feeds `diagnose`. Measured: **39 of 58** demo
jobs were handed a file out of the user's own work directory, and four gained
findings (`nccl`, `import-error`) read out of somebody else's training run. One
reviewer went further and dropped a fabricated traceback into the current
directory, which produced "GPU ran out of memory" and a verbatim traceback on
synthetic job 5100002.

`cli.main` now sets `args.no_logs = True` under `--demo`. That is not a workaround:
for synthetic records it is the *correct* answer, since no log exists to find. It
also restores what `DEMO_SITE` was added for — the demo renders identically on a
login node and a laptop.

### 4. The plain node table goes through `render.NODE_COLUMNS`

It was the one plain table still hand-formatted at `"  %-16s %9s %10s %20s  %s"`,
while the spec written for it sat unused and the dashboard used it. Now it goes
through `_plain_layout` + `text_table` like the other three:

```
before, any width          after, COLUMNS=80              after, COLUMNS=140
NODE          N   RATE     NODE               N   RATE    NODE                   N   RATE
gpu-compute-node-a100-0001     10/14          gpu-compute-node-a100…  10/14      gpu-compute-node-a100-0001  10/14
cn2       0/14                 cn2             0/14                   cn2         0/14
   (every column shifted 10 cells)      (aligned, 72 cells)      (aligned, name in full, 76 cells)
```

It drops columns on a narrow terminal, grows the name column on a wide one, and
lines up whatever the names are.

### 5. The workload banner wraps for real

`" ".join(render.wrap(evidence, 100))` puts the wrapped lines straight back
together — the width was dead code, and the evidence went out as one 138-cell line
at every terminal size. Now one `append` per wrapped line, each carrying the
two-space indent, at `_prose_width(self, 4)`. On an 80-column dashboard:

```
before  138 | 18 of 20 runs of cot-exp in test failed; 18 were TIMEOUT. Every one used the same …
after    74 |   18 of 20 runs of cot-exp in test failed; 18 were TIMEOUT. Every one used
         65 |   the same --time=00:30:00. 9 GPU-hours consumed by the failures.
```

Taking the panel's warning: the fix is a width-aware wrap, not merely dropping the
`join`, which would have reproduced #10 here.

### 6. A cut cell says it was cut

`render.clip` replaces the bare `value[:width]`, marking a truncated cell with `…`.
The case that made this worth doing is not the visibly-broken one:

```
node_list = midway3-0600,midway3-0611     column width 12
before    midway3-0600      a complete, valid, real name — for a job that ran on two
after     midway3-0600…
```

Truncating the column stays deliberate, as `Column`'s docstring says; doing it
without a marker was not, and every other truncation here announces itself.

### 7 & 8. Two flags that were accepted and thrown away

`render_sizing` takes a `sort` and iterates `sort_groups(...)`; the `--sizing
--json` branch does the same, so text and JSON cannot disagree. A non-default order
is now named on screen (`ordered by failure rate`), as the overview does — the
screen never said what order it was in, and its own note warns that "the workload
most worth re-sizing can sit at position 13", for which `--sort rate` is the
remedy.

`cli._load`'s demo branch applies `-p`, `-u` and `--failed`, and raises when
nothing matches. `--demo -p gpu` exited 0 printing all 58 records; it now exits 2
with "no demo jobs match partition gpu", matching the real path. An explicit job id
still bypasses the filters, as `-j` does against sacct.

### 9. The listing is indexed once, not per probe

`Scan._names_in` caches the membership set beside the listing `entries` already
caches. The set was being rebuilt on each of ~84 probes per job, so the test this
class exists to make constant-time was linear in the directory:

```
                 before        after
 1,000 files     2.7 us       0.4 us  per probe
13,000 files    16.6 us       0.9 us  per probe   (flat, as it should be)
```

Honest about scale, per the panel: unmeasurable on a small log directory, ~4% of
the whole log pass end-to-end, and worth it because it is three lines in the one
function whose entire docstring is a performance argument.

### 10. The dashboard measures the terminal, like the plain renderer does

New `tui._prose_width(screen, indent)`, used by `JobScreen` and `PatternsScreen` in
place of the fixed 86 and 82. `report._prose_width` had already solved this and
said why; `JobScreen._path_budget` had already solved it for paths on the same
screen.

```
terminal  70 -> widest line 67    (was 94, soft-wrapped to column 0)
terminal  80 -> widest line 78    (was 94)
terminal 120 -> widest line 118   (was 94 — refusing the room it had)
```

The narrow-terminal pair layout goes with it: `JobScreen` now passes
`render.PAIRED_LINE_WIDTH`-aware `max_value` to `pair_rows`, the threshold
`report` has applied all along. That was raised by one reviewer only, so it is
recorded as a partial fix — see **Open** below.

### 11. Disk I/O sums the steps that moved the data

`Job._io_from_steps` sums `read_bytes` / `write_bytes` over `work_steps`, for the
same reason `_from_steps` sums CPU, and against the same rejected alternative in
its own words: "Falling back to the largest step was wrong too: it drops every step
but one." Four `srun` steps each reading 30 GiB and writing 10:

```
              before        after      truth
read           30.0 GiB    120.0 GiB   120.0 GiB
write          10.0 GiB     40.0 GiB    40.0 GiB
io_rate      11.4 MiB/s   45.5 MiB/s
```

`io-heavy` was suppressed by this: four steps of 120 GiB in an hour is 136 MiB/s
against a 100 MiB/s threshold, reported as 34, so the finding whose whole purpose
is to say when the filesystem set the pace stayed silent. It now fires.

The panel's addition is folded in: `work_steps`, not `steps`, so a polluted
`.extern` claiming 500 GiB against 1 GiB of real work reports 1. Where **no** work
step recorded anything, extern is the only reading there is and the old `max`
stands as a fallback — the same shape `total_cpu` uses. The caveat both reviewers
raised is documented at the property: `TRESUsage*Tot` is a per-step total and sums
exactly, while the `MaxDiskRead` fallback beneath it is a per-task maximum and does
not — summing those still under-reports a multi-task step, by less than `max`,
which discarded every step but one.

### 12 & 13. Two small ones

`sort_groups` runs two stable passes for a descending mode instead of
`reverse=True`, which reversed the tie-break along with the primary. `recent` now
gives newest-first, then A→Z, like every other sort. And both node screens
pluralise: "1 node below threshold omitted".

### The test that let #4 through

`test_no_table_row_overruns_the_terminal` built five views in its helper and then
asserted over `("overview", "list")` — so the node table was exempt from the
invariant it was breaking, while the sibling rule test iterated all five and could
not catch it (a rule is drawn from the widest *row*). It now iterates every view,
and the helper carries a `nodes-long-names` view whose node names are 26
characters, because the demo's are 12 and that is what let a fixed `%-16s` survive
two audits.

This is the third round in which a *test* was the problem — after
`test_short_rows_do_not_crash` (a call compared with itself) and
`test_a_log_suffixed_name_is_answered_without_a_stat` (which asserted the very
behaviour that caused defect #11 of round two). Worth naming as a pattern: this
suite's failures are not missing tests but tests that assert less than they
appear to.

---

## Open

One thing is deliberately not fixed, named rather than left implied.

**`--demo` still ignores `-S` and `-E`.** Unlike `-p` and `-u`, the window is not
silently discarded: the screen says "synthetic demo data" instead of a date range,
so the output does not claim a filter it did not apply. Left alone.

### Closed in round five

**The job screen's gauges and detail rows below ~96 columns** — the entry that read
"raised by one reviewer of three and never put to a second panel". Round five's read
is that second reviewer, and it added what the first could not: the same rows break
under `--plain` identically, and they break at 80 columns, not merely narrow ones.

The decision that entry was holding out for still stands, though, and the fix
respects it. It declined "a width-adaptive bar … a real change to the row idiom this
tool shares with slurmwatch", and the bar is **not** adaptive: the row up to the
value column is a fixed 42 cells at every terminal size, so a 60% gauge looks the
same here as in the live view, and at 100 columns and up the output is unchanged
byte for byte. What was overrunning was the trailing `· detail`, which is prose and
now behaves like the rest of the prose on that screen. That is the drive-by the
entry was refusing, replaced by the smallest change that keeps the idiom intact.

---

## Consequence for the numbers

**Round five.** Two findings change what the tool *reports*, not how it renders.
Round five's #2 removes a CRITICAL from every `CANCELLED`, `TIMEOUT`, `PREEMPTED`,
`NODE_FAIL` and `OUT_OF_MEMORY` job that recorded signal 9 — so `slurmpast <jobid>`
now exits 0 on a job you cancelled yourself, where it exited 1 before, and any CI
step keying off that code sees the change. Round five's #1 moves the other way:
`slurmpast <many ids>` can now exit 1 where it exited 0, because ids past `-n` are
examined instead of dropped. Everything else is presentation, or the demo.

**Rounds one to four, below.**

Fixing 1 lowers `--time` advice for any workload holding a hung timeout at a
larger limit than its real ones. Fixing 11 raises `read_bytes`, `write_bytes`,
`io_bytes` and `io_rate` for any multi-step job — most `sbatch` scripts with more
than one `srun` — and will make `io-heavy` fire where it previously did not; it
also *lowers* them for any job whose `.extern` was over-reporting. Fixing 12
reorders same-day groups under `--sort recent`. The rest change presentation, exit
codes, or how long a log scan takes.
