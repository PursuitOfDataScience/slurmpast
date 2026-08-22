# slurmpast — audit and resolution

> **Release 0.7.0, 2026-08-22.** Eleven rounds (twenty-two through thirty-two),
> ten defects, all found by running the tool against a real cluster's accounting
> database and log tree rather than against fixtures. 1503 tests at 0.6.0,
> **1560** here.
>
> What a user gets that they did not have at 0.6.0: a traceback finding that shows
> the traceback, a clock speed in `--json` that is not wrong by 1000x, a workload
> comparison that holds the workload fixed, a node table that does not count a
> cancellation as a node behaving, no NCCL fault invented from the word NCCL, no
> "Nothing was computed" over 18.4 TiB of traffic, and a job list that finds a
> host by the name the job screen prints for it.

> **Round thirty-two, 2026-08-22.** **No defects.** The first round since the
> real-data streak began to find nothing, and it is recorded in full because a
> clean round is only meaningful if what was actually checked is written down.
> 1560 tests, unchanged; all four gates clean.
>
> Four probes, three of them against ground truth outside this repository:
> `compress_nodelist` validated by Slurm's own `scontrol show hostnames`; the
> parser fuzzed with 3,000 realistically corrupted real rows; and `sizing.py` held
> to the four rules its module docstring states, across 872 actionable
> recommendations.
>
> Three of my own checks reported violations that turned out to be the harness
> being wrong, not the code -- each time by using a looser definition of "evidence"
> than the module itself uses. `sizing.py` had already written the warning I
> tripped over: "Both numbers were right; they came from different runs."

> **Round thirty-one, 2026-08-22.** One defect: a hostname printed on the job
> screen that the job list could not find. 1553 tests before, **1560 after**; all
> four gates clean.
>
> `filter_jobs` names the standard it broke -- "typing what you can plainly see and
> getting an empty list is the worst kind of empty result" -- and offers `what died
> on midway3-0385` as one of the four queries the box exists for. Slurm folds a
> multi-node allocation to `midway3-[0003-0004]`, the raw string was what got
> searched, and neither hostname is in it.
>
> Two large checks found nothing and are recorded as carefully as the defect. Log
> discovery was tested against the real filesystem for the first time -- 8,161 jobs
> whose log exists under a searched root -- and **never once attached the wrong
> file**. And this cluster runs Slurm 20.11.8, which turned the field negotiation
> into a live test rather than a fixture: `StdOut`, `StdErr` and `SubmitLine` do
> not exist here, the tool dropped all three and asked for the other 80.

> **Round thirty, 2026-08-22.** One defect: a CRITICAL finding that denied, in
> plain words, the terabytes the WARNING directly beneath it was reporting. 1547
> tests before, **1553 after**; all four gates clean.
>
> Found by asking which findings co-occur on real jobs and which of those pairs
> pull a reader in opposite directions. Nine contradictory pairs were proposed and
> eight never occur; the ninth fires on 33 jobs, and reading one of them showed the
> tool naming a job's blocking call one line below an action telling the reader to
> go find it.
>
> The larger part of this round found nothing, which is worth recording as
> plainly as the defect. `render.py`'s reason for existing -- the dashboard and
> `--plain` cannot drift -- was tested directly for the first time and holds
> exactly: over 59 real jobs, every label and every value on one surface appears on
> the other. So do the overview's headline statistics, re-derived independently,
> and `--ascii` purity across 409 renderings.

> **Round twenty-nine, 2026-08-22.** One defect and the exemption that hid it: the
> machine-readable surface published a clock speed that reads 1000x wrong, on 85%
> of the real jobs carrying the field. 1542 tests before, **1547 after**; all four
> gates clean.
>
> Round twenty-eight asked whether a rule's *evidence* matches its promise. This
> round asked the same of a surface: `_job_json` opens "Deliberately exhaustive: if
> the tool read it, this emits it", and `docs/details.md` repeats it. Checking
> every `Job` value against the payload turned up one gap -- and the reason it had
> never been caught is the sharper half of the finding.
>
> Sixth "tests that assert less than they appear to", and the first that was
> *deliberate*: `TestTheJsonPayloadKeepsItsPromise` carries an allow-list written
> so "the next value that is not emitted has to be argued for here instead of
> passing quietly". One of its entries was an argument that was simply false, and
> it silenced exactly the finding the class exists to surface.
>
> Two further things were checked and are sound: every number 20,905 real jobs put
> into a finding reproduces from the record, and no finding's text shows an
> unfilled placeholder, a stray `None`, a percentage over 100 or a negative
> quantity.

> **Round twenty-eight, 2026-08-22.** One defect with two halves, and it is the
> largest-impact finding of the streak by share of affected output: a finding
> headed "Traceback tail from the log" was showing the tail of the **file**. 1535
> tests before, **1542 after**; all four gates clean.
>
> Round twenty-seven read real log contents for the first time and found a fault
> invented from a word. This round stayed in the same vein and asked the opposite
> question -- not "does the marker match something harmless?" but "when a rule does
> fire, is the evidence it prints the evidence it promises?" Of 27,435 readable
> logs, 486 hold a Python traceback and **173 of them (36%) rendered something
> that was not one**.
>
> Two measurements in this round were wrong before they were right, and both were
> corrected by re-running rather than by re-reading. The first probe compared a
> list's length against a string's character count and reported 1%; the second
> claimed no real log needs the rank-prefix half of the fix, on a scan that had
> missed 25,000 files. The numbers below are the ones a re-run reproduces.

> **Round twenty-seven, 2026-08-22.** One defect, from the first pass over real log
> *contents* rather than real job records: a CRITICAL "Collective communication
> fault" manufactured from the word NCCL. 1524 tests before, **1535 after**; all
> four gates clean.
>
> The round opened by re-verifying `nodes.py`, which had produced the previous two
> rounds' defects. Its statistics are sound in both directions -- and the finding
> that matters is *where* those two bugs were: not in the machinery but in the
> sample fed to it. The Fisher test, the correction and the intervals were never
> wrong; the stratum (round 25) and the denominator (round 26) were.

> **Round twenty-six, 2026-08-22.** One defect, and it moves a rate on real data:
> a cancellation counted as a placement the node handled fine. 1520 tests before,
> **1524 after**; all four gates clean.
>
> Found by making the "fixed only on one side" hunt systematic instead of
> incidental. Round twenty-five's bug came from two modules disagreeing about an
> identity, so this round asked the same question of a different invariant --
> **which jobs does each module count as evidence?** -- and drove seven marginal
> job shapes through `usable()`, the grouping, the node table and `sizing` to see
> where they disagreed.
>
> Six of the seven agreed. The seventh was a cancellation, and the disagreement was
> inside one module: excluded from the numerator, counted in the denominator.

> **Round twenty-five, 2026-08-22.** One defect, and it is the most consequential
> of the streak: the module whose entire reason for existing is holding a workload
> fixed was not holding it fixed. It changes a *rate*, not wording. 1514 tests
> before, **1520 after**; all four gates clean.
>
> `patterns.group_key` had this same defect and it was fixed there, in these words:
> "two people's unrelated `run.sh` on one partition became a single fabricated
> workload". `nodes.py` never got the fix. Seventh "fixed only on one side" in this
> record, and the first to move a number a reader acts on.
>
> Found by running `--all-users --nodes` -- a combination in the README's own
> examples -- against the real cluster and asking why a 486,882-job query had
> reduced itself to 17 placements of one stranger's workload.

> **Round twenty-four, 2026-08-22.** Real data, widened from one user to the whole
> cluster: 471 users, 486,882 jobs in two days, and states, id shapes and string
> lengths no single account contains. Two defects. 1498 tests before, **1514
> after**; all four gates clean.
>
> The cluster is where the *shapes* live. A pending throttled array is spelled
> `49046820_[1-20%10]`, which sacct prints in its own JobID column and then refuses
> in `-j`. The longest job name is 123 characters with no space in it. Neither
> exists in one user's history and neither could be invented by a fixture author
> who had not seen sacct emit it.

> **Round twenty-three, 2026-08-22.** Real data again, pushed harder: all 15,085
> jobs through the post-mortem renderer, and the dashboard driven against 930 real
> workloads. Two defects -- one a sentinel rendered as a hostname, one the slowest
> interaction in the app doing twice the work. 1487 tests before, **1498 after**;
> all four gates clean.
>
> The second is also a lesson about method. My first account of it blamed a
> provisional mount-time column width; the trace meant to confirm that showed both
> builds computing an *identical* layout, and the fix I then wrote to defer the
> mount build measured 3.64s against the plain guard's 3.55s. It is not in the tree.
> Two wrong explanations, both caught by measuring instead of reasoning.

> **Round twenty-two, 2026-08-22, after the 0.6.0 release.** The angle none of the
> twenty-one rounds before it used: **run the tool against this cluster's real
> sacct data.** Every previous round used `--demo` or a hand-built fixture. One
> defect, in two halves, and it was the first thing real data showed. 1476 tests
> before, **1487 after**; all four gates clean.
>
> 15,085 real jobs over 90 days. `find_memory_search` produced three findings and
> **two of them described a search that never happened** -- 71 OOM kills at an
> unchanged 6.0 GiB, and 16 at an unchanged 8.0 GiB -- the first rendering 777
> characters of `6.0 GiB -> 6.0 GiB -> ...` under a heading calling it a search.
>
> Fixing it then exposed a *fixture* asserting the same thing: a test that had been
> pinning "a search" over five identical values since it was written.

> **Round twenty-one, 2026-08-22.** One defect, and CI found it rather than any
> local gate: `tests/test_portability.py` imported `tomllib`, stdlib from **3.11**,
> in a package declaring `requires-python = ">=3.10"`. Four assertions died with
> `ModuleNotFoundError` on the py3.10 and oldest-Textual jobs after passing every
> local run -- because a local run is one interpreter.
>
> The irony is worth keeping: the test that failed is
> `TestTheToolsDeclareWhatTheyImport`, whose entire subject is declaring what you
> import. `tomli` is in the dev extra behind a `python_version < '3.11'` marker
> now, the import is guarded, and `TestNothingImportsPastTheDeclaredPythonFloor`
> makes the class catchable locally: it parses every module in `src/`, `tests/` and
> `tools/` for unguarded imports of stdlib modules that postdate the declared
> floor. Its control asserts it reports the exact line that shipped.
>
> **The lesson, recorded because it generalises past this repo:** four green gates
> on one interpreter is not the same as CI. The gates verify the code; the version
> matrix verifies the *declaration*, and only the second can see a floor violation.

> **Round twenty, 2026-08-21, continuing the same request. No defects.** The first
> round of the streak to find nothing, from two angles chosen because neither had
> been tried and both cover ground everything else depends on. 1471 tests before,
> **1473 after** -- the two are the property tests this round wrote for what it
> checked by hand.
>
> **`fit_columns`, over 40,000 generated specs.** Every table on every surface goes
> through it, and it was pinned only by the four specs this codebase happens to
> declare. Its docstring makes six promises; all six hold at generated widths,
> paddings, content caps and `fill_to` values. The generator is checked for
> vacuity, because a green fuzz whose assertions never ran is worth nothing:
> 9,737 trials dropped a column, 22,308 grew a flex column, 14,987 could reach
> `fill_to` and 4,377 hit the floor case where the table legitimately cannot fit.
>
> **Every reproduction from rounds fourteen to nineteen, re-run.** 34 of them,
> driven the way each was first observed rather than through the tests written
> afterwards -- round six's method, applied to six rounds instead of one. None
> still reproduces.

> **Round nineteen, 2026-08-21, continuing the same request.** One defect, and it
> is the fifth instance of this repo's named failure mode: a fix applied to one of
> the two modules that make the claim. 1438 tests before, **1471 after**; all four
> gates clean.
>
> Round eighteen asked whether two findings on one job contradict each other. This
> round asked it one level up -- whether a **cross-run** finding contradicts the
> **per-job** finding it sits above on the workload screen -- and then whether
> `sizing`'s numbers are right at all.
>
> `sizing` came back clean, and the way it came back clean is worth as much as the
> defect: 569 actionable suggestions over 400 generated workloads with a planted
> peak, and not one lands below what the workload was measured to need. That
> invariant is the module's whole reason for existing and nothing had ever asserted
> it; it is a property test now.

> **Round eighteen, 2026-08-21, continuing the same request.** Four defects, from
> the first angle none of the previous rounds used: not *does a view survive its
> input* but **does one finding contradict the finding printed above it**.
> 1411 tests before, **1438 after**; all four gates clean.
>
> Found by enumerating every finding set `diagnose` can produce over 12,000
> synthetic jobs built from (state, exit code, signal) triples sacct actually
> records, then reading the pairs. 267 distinct finding sets, 69 distinct pairs,
> four of them saying opposite things about the same job.
>
> The statistics were the round's other target and came back clean: Fisher exact
> agrees with scipy to 8e-13 over 5,986 comparisons, Wilson with statsmodels to
> 9e-06 over 20,099 intervals (the gap is z=1.96 against the exact quantile,
> invisible at one decimal), and Benjamini-Hochberg exactly over 3,000 random
> families.

> **Round seventeen, 2026-08-21, continuing the same request.** One defect, in the
> two screens a reader spends all their time in, and reachable by pressing one key.
> 1396 tests before, **1411 after**; all four gates clean.
>
> Round sixteen fixed an empty grid on the node screen. This round asked the
> obvious next question -- *what do the other tables do when they have no rows?* --
> and the answer was worse, because theirs needs no unusual history at all: filter
> to `failed` on a week that went well, or mistype a search.
>
> The rest of the round is negative: every plain renderer and every screen was
> driven through eleven degenerate histories (empty, one job, no name, no node, no
> timestamps, no TRES, every field blank) at 90 columns. No crash, no overrun, one
> finding. Recorded so the next round starts somewhere else.

> **Round sixteen, 2026-08-21, continuing the same request.** Three defects, all
> found by driving the app with a *small* history rather than the 58-job demo.
> 1375 tests before, **1396 after**; all four gates clean.
>
> The demo is why they survived sixteen rounds: it has 58 jobs, eight workloads and
> a node that eats them, so no count in it is ever 1 and no view of it is ever
> empty. Every reproduction below is a history of one or five jobs -- which is what
> a first-time user has, and what `--demo <jobid>` shows them.
>
> `logs.py` was the other half of this round and produced nothing: twelve documented
> behaviours driven against a real filesystem, all twelve correct. Recorded so the
> next round does not re-run them.

> **Round fifteen, 2026-08-21, continuing the same request.** Three defects and a
> test that could not have caught any of them. 1357 tests before, **1375 after**;
> all four gates clean, assets regenerated.
>
> Round fourteen swept the two *rendering* surfaces against each other. This one
> adds the third -- `--json` -- and asks a different question of all three: not "do
> they word it the same" but **"does each of them carry the same warnings"**. The
> answer was no, and the worst case is the dashboard telling you to cut a GPU job
> from six cores to two with the sentence "cutting them can starve the GPU" removed.

> **Round fourteen, 2026-08-21, continuing the same request.** Seven defects, all
> of them the dashboard doing on its own what `render.py` exists to do for both
> surfaces -- plus a key that answered on four screens out of six. 1314 tests
> before, **1357 after**; all four gates clean, assets regenerated.
>
> `CLAUDE.md` says "`render.py` exists so the dashboard and `--plain` cannot
> drift", and round seven enforced that for whole sentences. This round is what the
> sentence-level sweep cannot see: the *fragments* under its 25-character floor and
> the *arithmetic* neither file shares. Two of four fragments had already come
> apart, and one of them had quietly disabled `--ascii` on the glyph it points at.

> **Round thirteen, 2026-08-21, continuing the same request.** One defect: the
> search box invited three things the landing screen cannot match, so typing any of
> them returned an empty list. 1308 tests before, **1314 after**; all four gates
> clean.
>
> Same root cause as most of this streak -- one feature described in three places
> and behaving like none of them -- but reached from a new direction: comparing a
> promise the UI makes against what the code behind it actually does.

> **Round twelve, 2026-08-21, continuing the same request.** One defect, in the
> build tooling rather than the app: the GIF generator declared none of the packages
> it imports, while its own docstring claimed a dev install brought them in. 1304
> tests before, **1308 after**; all four gates clean.
>
> Mostly negative results again, and four of them are structural checks worth not
> repeating: `compress_nodelist` is a clean inverse of `expand_nodelist` over 4,000
> fuzzed hostlists, the job-LIST table agrees cell for cell across both surfaces,
> and every value `goodput()` and `node_table()` compute is reachable -- two that
> looked dead turned out to be surfaced wholesale by `--json`.

> **Round eleven, 2026-08-21, continuing the same request.** One defect, and it is
> the third instance of the same root cause -- a value `render.py` supplies that only
> one of the two front ends consumes. 1299 tests before, **1304 after**; all four
> gates clean, assets regenerated.
>
> The round is mostly negative results, and they are worth as much: the dashboard
> survived 2,400 random keypresses across sixty sessions without a crash, the layout
> engine holds its contract at every width from 10 to 260 cells, and a field-by-field
> diff of the job post-mortem across both surfaces on seven jobs found exactly the
> one disagreement below. Those are recorded so the next round does not re-run them.
>
> Round eight's `--ascii` test caught a regression in this round's own fix on its
> first run, which is the best argument for it that could be made.

> **Round ten, 2026-08-21, continuing the same request.** Four defects, found by
> fuzzing the parser rather than reading it and by cross-checking the three surfaces
> against each other. 1269 tests before, **1299 after**; `ruff`, `ruff format` and
> `mypy` clean at both ends.
>
> The first is the worst thing found across these four rounds: a single record whose
> `Elapsed` did not parse turned the GPU-hour and core-hour totals for an entire
> history into `nan` -- destroying every *other* job's figure -- and then raised
> `ValueError` out of the job screen. The second is this suite's named failure mode
> caught in the act: a test called `test_one_job_is_not_reported_as_one_jobs` has
> been green for rounds while the landing screen said "1 jobs in 1 workload",
> because it navigates away from that screen before it looks.

> **Round nine, 2026-08-21, continuing the same request.** Into the two modules the
> previous two rounds never opened: `demo.py` and the state table in `sacct.py`.
> Three defects, one of them visible in the README's own lead image. 1260 tests
> before, **1269 after**; `ruff`, `ruff format` and `mypy` clean at both ends, and
> the committed assets regenerated.
>
> The demo one is the round's lesson. Every one of the 58 synthetic jobs carried an
> `End` that its own `Elapsed` contradicts -- twenty hours on screen against thirty
> minutes, two rows apart -- and the whole suite passed, because nothing had ever
> asserted the demo's clock agrees with itself. Round five caught the sibling of it
> in `_time_of_day` and did not look at `End`. That is this suite's named failure
> mode, "tests that assert less than they appear to", in the fixture the screenshots
> and the GIF are cut from.

> **Round eight, 2026-08-21, from the round-seven tree.** A second pass over the
> same request, into the parts round seven did not reach. Four defects, all of them
> a flag or a screen that half-works. 1221 tests before, **1260 after**; `ruff`,
> `ruff format` and `mypy` clean at both ends.
>
> Two are the same shape round seven found, in places it did not look: `--ascii` was
> accepted and discarded by five of the six plain views, and `HelpScreen` was the one
> surface rounds five, six and seven all skipped when they wrapped the prose -- so
> the screen whose job is explaining the app was the last one still breaking its own
> layout. The third is a cross-surface disagreement of exactly round seven's kind,
> found by driving both front ends with a job name long enough to matter.

> **Round seven, 2026-08-21, from `b178312`.** Asked to evaluate the codebase and
> fix what it found, with the app and the UI working and no major changes wanted --
> so: polish. Thirteen defects, no new features, no behaviour moved. All four gates
> were run for real, before and after: 1195 tests before, **1221 after**, `ruff`,
> `ruff format` and `mypy` clean at both ends.
>
> The theme is one rule of this repo's own that had gone unenforced. `CLAUDE.md`
> says "`render.py` exists so the dashboard and `--plain` cannot drift"; seven
> sentences were still written out in both front ends, and one pair had already come
> apart -- `--plain` ended the exclude disclaimer at "trades availability for
> reliability." while the dashboard went on ", and that is your call.". Nothing on
> either screen could show a reader that, because only one of the two is ever on
> screen at a time. The other twelve are what a sweep for the same shape turned up:
> nine unguarded singular/plurals, two guessed wrap widths in the module whose own
> docstring says not to guess them, and a version boundary the code states carefully
> in two places and contradicts in three.
>
> Every one was reproduced by running the code, and each fix ships with its control.

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

## Round thirty-two — nothing found, and what was looked at

No code changed this round. The value of the round is the list below, so a later
one does not spend itself re-checking the same ground.

### `compress_nodelist`, against `scontrol show hostnames`

This is the one output a user pastes straight into a submission script, so the
standard is not "our round trip agrees with itself" but "Slurm accepts it and
expands it to the nodes we meant". 57 cases were built from this cluster's real
607-node fleet -- random scatters of 1 to 40 nodes, contiguous runs at four
offsets, the `beagle3-bigmem` group, 63 midway3 nodes, and the entire fleet at
once -- compressed, then handed to `scontrol`:

```
real nodes on this cluster: 607
cases: 57   our round trip failed: 0   slurm disagreed: 0
```

### The parser, on 3,000 corrupted real rows

250 real sacct rows, each mutated twelve ways: truncated, a field dropped, a
field added, everything emptied, a 40-digit number, a negative, `wörk—dir…✓`, an
embedded newline, an embedded `|`, a NUL byte, a 5,000-character value, and
nothing but delimiters. Each result was pushed through `parse`, `diagnose`,
`render_job`, `filter_jobs` and `History.stats`. **No exception, anywhere.**

One asymmetry was examined and left alone. `parse` drops a row with more fields
than were requested -- documented, because "every column after the offending one
would be shifted" -- but accepts one with fewer, where the same shift can occur:

```
  intact             -> state='CANCELLED by 940740146'
  one field dropped  -> state='0:0'          <- ExitCode, shifted into State
  one extra field    -> row REJECTED
```

It is not filed as a defect because it is not reachable. The `>` case is what the
docstring is about -- a value containing the delimiter makes a row *longer* -- and
all 68,222 real rows here carry exactly the 80 fields requested. Recorded so the
asymmetry is a known choice rather than an oversight.

### `sizing.py`, against the four rules it states about itself

872 actionable recommendations over 1,528 real workloads. Every rule holds:

* **Never size walltime down from a TIMEOUT** -- no `--time` suggestion falls
  below what its own evidence proves, counting completed non-hung runs and the
  limits that truncated computing timeouts.
* **Never treat a hung run as evidence of needing more time** -- no mostly-hung
  workload is told to raise its limit.
* **Never size memory from MaxRSS above the cgroup limit** -- no `--mem`
  suggestion sits below the highest trustworthy peak.
* **Say "not enough evidence" rather than guess** -- no actionable number appears
  below `MIN_RUNS`.
* And the unit claim: `--cpus-per-task` is advised per task. The one apparent
  violation -- 26 cores/task on a 30-core allocation -- was the harness reading
  `max(task_count)` and `max(cpu_count)` from two different runs of a
  heterogeneous group. The busiest run is single-task, 21.7 of 24 cores busy,
  and 27 is right.

### On the three false alarms

All three came from the same mistake: checking a module against a plausible rule
rather than the rule it states. `memory_advice` excludes `looks_like_noop` runs
from its evidence and `walltime_advice` floors on a computing timeout's *limit*
rather than its elapsed; harnesses that ignored both produced 13 and 8
"violations" respectively, and 193 more came from counting completed runs where
the module counts usable observations. Worth writing down because it is the
failure mode of an audit, not of the code: a finding measured against the wrong
standard looks exactly like a real one until you read the source.

## Round thirty-one — the hostname on screen that search could not find

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `filter_jobs` searched the folded `NodeList` as stored, so no hostname inside a multi-node range matched the job that ran on it | `index.py:301` | `TestAFoldedNodeListIsSearchableByHostname` |

### 1. "peak on midway3-0003", and the list says no such job

Slurm compresses a multi-node allocation. The search haystack took `job.node_list`
verbatim, and `midway3-[0003-0004]` contains the string `midway3-0003` nowhere.

The reader is not guessing at those names -- the job screen prints them. Real job
51553906, rendered:

```
    nodes            midway3-[0003-0004] (2 nodes)
    slowest task     0.3% below average (task 1 on midway3-0003)
    peak on          midway3-0003 task 0
```

Two rows name `midway3-0003`. Typing it into the job list returned nothing, on a
history that contained the job. `filter_jobs`' own docstring calls this out in
advance, about a different column:

> Typing what you can plainly see and getting an empty list is the worst kind of
> empty result -- it reads as missing data.

and offers `what died on midway3-0385` as one of the four things the box is for.

Measured here: 26 of 20,905 jobs carry a folded NodeList, and 72 hostname searches
came back empty for a job that had run on that node. After the fix, 0 do, and
`midway3-0003` returns its 44 rows in 29 ms across the whole history -- the common
path is untouched because 20,879 of the jobs have no bracket to expand.

`nodes.expand_nodelist` already did this work for the reliability table, and is
bounded by `MAX_EXPANSION`; the raw string stays in the haystack beside the
expansion, so a reader who copies the bracketed form off the `nodes` row still
matches. Four of the seven new tests are controls, including one that a
match-everything "fix" would fail.

### Consequence for the numbers

No statistic changes. One search returns rows it should always have returned:
here, 26 jobs become findable by the names of the 2-4 nodes each ran on.

### What was verified and not changed

* **Log discovery, against the real filesystem for the first time.** 23,647 log
  files were indexed by the job ids in their names, giving 8,161 jobs whose log
  demonstrably exists under a root the tool searches. On an 800-job sample
  `assign_logs` attached **the right file 121 times and the wrong file 0 times**.
  Never attaching another job's log is the property that matters, since a wrong
  log means a wrong diagnosis, and it holds.
* The 679 misses are all outside the documented search scope, and are left alone
  deliberately: 457 sit at `logs/<subdir>/<file>`, one level below the `logs`
  entry in `_SUBDIRS`, and the rest are under names the tool never claimed to
  search (`midtraining`, `results`, `work`). Deepening the walk is a scope and
  cost decision, not a defect fix; `--log-dir` already covers it.
* **Field negotiation, on a cluster old enough to test it.** This machine runs
  Slurm 20.11.8. `StdOut` and `StdErr` arrived in 24.05 and `SubmitLine` in 21.08,
  so all three are genuinely absent -- `supported_fields`/`resolve_fields` dropped
  exactly those and queried the remaining 80 without error. The JSON payload's
  `stdout_pattern`, `stderr_pattern` and `submit_line` are correctly null here
  rather than empty strings.
* Every searchable field is searchable by its displayed value: 6,000 jobs were
  probed with their own job id, name, state, partition, node list and start
  timestamp in three formats (`2026-07-28`, `07-28`, `07-28 15:00`). Zero
  returned nothing before the fix, and the folded NodeList was the only gap.

## Round thirty — "Nothing was computed", over 18.4 TiB of traffic

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `noop-allocation` said "Nothing was computed" and "Find the blocking call" on jobs whose `io-heavy` finding, rendered directly below it, reported terabytes moved at a sustained rate | `diagnose.py:341` | `TestNothingWasComputedIsNotSaidOverTerabytes` |

### 1. The tool named the blocking call one line under an order to go find it

`_cpu_rules` states the standard it is held to, in a comment guarding three job
states:

> "Find the blocking call" is advice about the user's own code, and it is only
> honest when nothing else already explains the missing CPU time.

`OUT_OF_MEMORY`, `NODE_FAIL` and `PREEMPTED` were guarded on that basis in round
eighteen. A *measurement* on the same record was not. Real job 36362003 rendered:

```
  [critical] Allocation did essentially nothing
      18:52:05 of wall clock, 3.5s of CPU, holding 4 GPU(s). Nothing was computed.
      -> Find the blocking call. If this allocation is a deliberate reservation,
         mark it so and this rule will stay quiet.

  [warning] Filesystem may be setting the pace, not the GPU
      read 18.4 TiB, wrote 15.1 GiB — 284.4 MiB/s sustained over 18:52:05.
```

Eighteen point four terabytes, read at 284 MiB/s for nineteen hours, described as
nothing. The reader is sent into their own code after a hang that is not there,
while the answer sits in the next finding down.

Measured over 20,905 real jobs:

```
jobs told 'Nothing was computed'            : 986
  of those, moving at least the IO floor    : 287
  of those, ALSO flagged io-heavy alongside :  33
total data moved by allocations told nothing was computed: 419.3 TiB
```

The finding stays CRITICAL and stays raised -- an allocation holding four GPUs
for nineteen hours to feed a filesystem is wasting them however it got there.
What changes is that it stops contradicting its neighbour:

```
  [critical] Allocation computed almost nothing — it was moving data
      18:52:05 of wall clock, 3.5s of CPU, holding 4 GPU(s), and 18.4 TiB of
      filesystem traffic at 284.4 MiB/s. The time went to I/O, not to compute.
      -> Treat this as the I/O problem below, not as a hang: stage the input
         somewhere faster, or overlap the transfer with compute.
```

`_io_explains_idle_cpu` deliberately reuses `_io_rules`' own two thresholds rather
than picking a third. The defect is two findings on one screen disagreeing, so the
guard has to fire on exactly the jobs the other rule fires on -- 33 of the 986,
not a similar-looking set. The 287 that clear the volume floor but trickle keep
the original wording, and a hang with no I/O at all is untouched, which is what
three of the six new tests pin.

### Consequence for the numbers

No statistic moves. `looks_like_noop` is unchanged, so `noop_jobs` (1391 here),
`gpu_hours_noop` (3338) and the overview's "in allocations that never computed"
are all the same figures as before -- and remain correct, because an I/O-bound
job's GPUs genuinely did not compute. Only the wording of one finding changes,
on the jobs where it was false.

### What was verified and not changed

* **`render.py`'s reason for existing, tested directly for the first time.** Both
  surfaces were rendered for 59 real jobs and diffed fact by fact: every label
  `job_sections` produces appears on both, and so does every value. 0 gaps in
  either direction. The patterns and nodes screens agree number-for-number too.
* The overview's tail note (`… 1503 more workloads (14365 runs) holding 20.1% of
  the compute`) is absent from the dashboard, and that is correct rather than
  drift: the dashboard's table holds all 1528 workloads and scrolls, so there is
  no truncation for it to name.
* Every headline statistic re-derived independently and matched exactly:
  completion rate 78.3%, 11,674 GPU-hours total, 3,337.5 idle, goodput 0.6578,
  noop fraction 0.2859, 6 open records excluded.
* `--ascii` output is pure ASCII across all six aggregate views and 403 job
  screens built from real records.
* `ascii_fold` rewrites seven characters and is applied to finished text, so it
  would rewrite a data value containing one. No data field in 20,905 real jobs
  contains any non-ASCII character at all, so this stays a hypothesis and is not
  filed as a defect.
* Eight further contradictory pairs were looked for and do not occur:
  memory-slack with host-oom or rss-above-limit, walltime-slack with either
  timeout finding, timeout-hang with timeout-real, and noop-allocation with
  system-cpu-heavy.

## Round twenty-nine — a machine surface that published the ambiguity

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `--json` emitted the raw `AveCPUFreq` string and withheld the resolved hertz, so a consumer read 3 MHz where the dashboard showed 3.00 GHz | `cli.py:473` | `TestTheResolvedClockIsMachineReadable` |
| 2 | the exhaustiveness test exempted `cpu_freq_hz` as "recoverable from `cpu.frequency`", which it is not | `tests/test_audit.py` | same class; the exemption is gone |

### 1. 17,503 of 20,550 real jobs published a figure that reads 1000x low

`duration.parse_cpu_freq` exists precisely because this field cannot be read as
printed. Its own docstring:

> Slurm's magnitude suffix is applied to a kHz base in some code paths and a Hz
> base in others, so the string alone is ambiguous by a factor of 1000.

It resolves that by trying both readings and keeping whichever lands in a
plausible clock range, and returns `None` when neither does. `render.py:1215`
builds the dashboard's "avg clock" row from the resolved number. The payload
emitted the string.

```
jobs with an AveCPUFreq string      : 20550
  string reads 1000x wrong          : 17503  (85%)
  tool drops it as uninterpretable  :  2061
  string and tool agree             :   986

most common misreadings:
    3984  3.00M -> tool says 3.00 GHz, the string reads as 3 MHz
    3040  3M    -> tool says 3.00 GHz, the string reads as 3 MHz
    1792  800K  -> tool says 800 MHz,  the string reads as 1 MHz
```

The 2,061 are worse than wrong, they are unanswerable: `385K` resolves to neither
a plausible kHz nor Hz reading, so the dashboard omits the row entirely -- and the
payload published `"385K"` with nothing to say it should not be believed.

The fix is the rule the payload already states two lines further down, about
`req_mem_raw` sitting beside `limit_bytes`: *"both are emitted so a consumer never
has to guess which convention a figure is in."* `cpu.frequency_hz` now carries the
resolved number, `null` where the tool will not vouch for it, and `cpu.frequency`
keeps the raw string unchanged so nothing downstream breaks.

### 2. The allow-list that silenced it

`TestTheJsonPayloadKeepsItsPromise` reads `_job_json` with `ast` and holds every
`Job` value to it, with exemptions "listed by name rather than inferred, so the
next value that is not emitted has to be argued for here instead of passing
quietly". Under the heading *Derived views of emitted numbers* -- "each is
recoverable from something that is emitted, so emitting it as well would be the
same number under two names" -- sat:

```python
"cpu_freq_hz": "cpu.frequency",
```

It is not recoverable from `cpu.frequency`, and on 85% of real jobs it is not the
same number. The other four entries in that group were re-checked and are sound:
`cores_busy` is `cpu.utilization x shape.cpus`, `fs_disk_bytes` is a documented
alias of `read_bytes`, and the `*_alloc` spellings are the allocation-row fallback
the emitted properties already read through.

A mechanism for making omissions argue for themselves only works if the arguments
are checked. This is the sixth "tests that assert less than they appear to" in
this record and the first that was written deliberately rather than by oversight.

### Consequence for the numbers

`--json` grows one key per job, 95 to 96; README and `docs/details.md` both
carried the old count and are updated. No text surface changes -- the dashboard
and `--plain` were already right, which is what made the drift invisible.

### What was verified and not changed

* Every number quoted by a finding across 20,905 real jobs reproduces from the
  job record: `walltime-slack`'s elapsed, limit and percentage, `timeout-real`'s
  limit, `timeout-hang`'s elapsed. No finding fires with an elapsed above its own
  limit.
* No finding's rendered text on those jobs contains an unfilled `%s`/`{}`, a
  stray `None`, a doubled space, a percentage over 100, a negative quantity, or
  an empty parenthesis. 18 findings across 27,000 checks matched a
  "dangling preposition" pattern; all 18 were the regex mis-reading a legitimate
  sentence end.
* `shape.req_cpu_freq_min`/`max` are raw strings too and stay that way: the tool
  never resolves them anywhere, so unlike `AveCPUFreq` there is no better answer
  being withheld.
* The rest of the payload's raw/resolved pairs are consistent -- `state_raw` with
  `state`, `job_id_raw` with `job_id`, `req_mem_raw` with `limit_bytes`,
  `alloc_gres`/`alloc_tres` with `gpu.count`.

## Round twenty-eight — a traceback tail that was the file's tail

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `_traceback_tail` took `lines[start:]` to EOF, so anything printed after the traceback became the "traceback tail" a reader was shown | `diagnose.py:638` | `TestTheTracebackTailEndsWhereTheTracebackEnds` |
| 1b | the same function's header scan did not strip torchrun's `[rankN]: ` prefix, so a log whose every traceback is prefixed produced no finding at all | `diagnose.py:638` | `test_a_torchrun_only_traceback_is_found_at_all` |

### 1. 173 of 486 real tracebacks rendered as something else

A traceback is frequently *not* the last thing in a log file. A wrapper retries,
torchrun prints its own summary, a shell banner follows, slurmstepd appends the
kill notice. The function scanned backwards for the last `Traceback` header --
correct, the one that killed the job is the last -- and then took everything from
there to the end of the file. The six-line trim kept the header, an ellipsis, and
the last four lines **of the file**.

On `report/4-train.err`, the rule promised a traceback and delivered the shell's
epilogue:

```
before   Traceback (most recent call last):
           ...
         slurmstepd: error: Detected 1 oom-kill event(s) in StepId=53371939.batch cgroup.

after    Traceback (most recent call last):
           ...
         torch.distributed.elastic.multiprocessing.errors.ChildFailedError:
```

The line the reader needed -- the one naming what the process actually raised --
was the line the trim discarded.

Measured across every readable log on this machine:

```
log files read                                : 27435
  containing a traceback                      : 486
  where the rendered tail CHANGED             : 173  (36%)
  where the old code found no traceback at all: 3
```

A traceback ends at its exception line: the first line after the header carrying
no leading whitespace, because frames are indented and the exception line is not.

### 1b. And three logs where the rule never fired

The same fix needs `[rankN]: ` stripped before the indentation test, or torchrun's
prefix makes the first frame look unindented and cuts the tail to one line. The
backward header scan needed the identical strip for a separate reason, found by
writing the test for the first half: when *every* copy of the traceback is
prefixed, the scan matches nothing and there is **no finding at all**.

torchrun normally prints its own wrapper traceback unprefixed beside the worker's,
which is why 50 of the 53 prefixed logs were found anyway. Three were not, and one
of them died on a line a reader would have wanted immediately:

```
[rank0]: AttributeError: '_OpNamespace' '_moe_C' object has no attribute 'grouped_topk'
```

Stripping in one of the two tests and not the other is the shape this record has
now named eight times. Both halves cost one call.

### Consequence for the numbers

No rate, interval or ranking moves -- this is evidence text, not statistics. What
changes is what 173 of 486 traceback findings display, and whether 3 logs produce
a traceback finding at all. A reader who acted on the old evidence was reading the
end of the file under a heading that said otherwise.

### What was verified and not changed

* Every fixture in the suite puts the traceback last, which is the 64% case that
  always worked; two of the seven new tests pin it and pass against the reverted
  tree, which is what makes them controls rather than decoration.
* The backward scan itself is right and was left alone. A log holding several
  tracebacks should show the last, and a chained `During handling of the above
  exception` block is not reached because the scan already landed past it.
* `cuda-oom` and `import-error` markers were re-checked over the same corpus and
  are clean: every hit is a FAILED job.
* Round twenty-seven's narrowed `_NCCL_MARKERS` holds up on the wider corpus --
  the surviving hits are genuine, three of them ending on `NCCL WARN Cuda failure
  'CUDA driver version is insufficient for CUDA runtime version'`.

## Round twenty-seven — a fault invented from the word NCCL

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `_NCCL_MARKERS` held the bare substring `"nccl"`, so any distributed job's startup or shutdown line drew a CRITICAL interconnect fault | `diagnose.py` | `TestMentioningNcclIsNotAnNcclFault` |

### 1. Ten real logs mention NCCL; none of them faulted; all ten were flagged

Every distributed PyTorch job prints NCCL when it starts and when it stops. The
marker tuple matched the word, so the finding was manufactured out of:

```
[rank0]:[W818 12:54:11 ProcessGroupNCCL.cpp:1524] Warning: WARNING:
    destroy_process_group() was not called before program exit
INFO [parallel_state.py:1208] ... distributed_init_method=... backend=nccl
NCCL version 2.19.3+cuda12.1
NCCL INFO Bootstrap : Using eth0:10.50.221.11<0>
```

Measured over 400 real log files on this machine: **ten mention NCCL, none of them
faulted, and every one of the ten drew the finding.** Two of those jobs had a
genuine CUDA OOM, so the post-mortem showed two CRITICALs -- one correct, one
sending the reader to debug an interconnect that was fine while the actual fix was
a smaller batch:

```
before   findings: ['cuda-oom', 'nccl', 'traceback']
after    findings: ['cuda-oom', 'traceback']
```

Only real logs could show it. Every fixture in the suite passed a string that *was*
a fault, so the loose marker was never exercised as a false positive -- and both
pre-existing NCCL tests still pass untouched, because `"nccl timeout"` and
`"NCCL WARN Watchdog caught collective operation timeout"` are fault shapes.

The replacement set is checked in both directions rather than tightened by
intuition: **zero hits across those ten logs**, and hits on all five real fault
shapes -- the watchdog timeout, `DistBackendError: NCCL error`,
`ncclUnhandledCudaError`, `ncclInternalError`, and NCCL's own `NCCL WARN` channel,
which it uses for trouble rather than for chatter. A guard test asserts no marker
is short enough to be a bare mention.

### The negative result: the node statistics, re-verified end to end

Rounds twenty-five and twenty-six both found defects in `nodes.py`, so this round
re-measured what it claims. `dominant_workload`'s docstring cites a simulation --
"3.73% ... and 3.17% ... under the 5% target either way" -- and both of those
rounds changed the sample it is computed from.

**False positives, every node genuinely identical:**

```
nodes  per node  nodes/job  p(fail)   flagged
10     30        1          0.20      4.5%
20     30        1          0.20      3.0%
10     30        1          0.05      1.2%
20     30        4          0.20      1.5%
10     30        4          0.20      0.5%
```

Still under 5%, and consistent with the recorded figures. The multi-node rows are
new: one job spanning four nodes contributes four *correlated* observations, which
the Fisher test treats as independent, so the concern was that it would inflate
the rate. It does the opposite -- correlated outcomes make every node look alike,
which makes the test conservative.

**Detection power, one node genuinely worse:**

```
nodes  nodes/job  p(good) -> p(bad)   found    innocent flagged
10     1          0.10 -> 0.50        98.3%    0.3%
10     1          0.10 -> 0.30        53.3%    1.3%
20     1          0.10 -> 0.50        96.7%    2.3%
10     4          0.10 -> 0.50        66.0%    0.3%
10 (60/node) 4    0.10 -> 0.50        99.3%    0.0%
```

Sound in both directions, and the innocents are within the FDR the correction
targets by design. Multi-node allocations cost power rather than correctness, and
recover it with more placements.

So the machinery was never the problem. That is worth writing down: two rounds of
defects in this module were both about *which observations reach it* -- the wrong
stratum, then an uninformative denominator -- and none about the arithmetic.

---

## Round twenty-six — an unknown outcome scored as a success

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A cancelled placement was excluded from the failure numerator and left in the denominator, scoring it as a node behaving | `nodes.py` `node_table` | `TestACancellationIsNotASuccess` |

### 1. "Cancellations excluded -- ambiguous", except from the denominator

`_bad` says it in its own docstring, and it is true of `_bad`. The table around it
counted every usable placement as a trial, so twenty cancellations on a node
arrived as twenty observations of that node not failing.

That is the one thing this module does that the rest of it argues against.
`index` states the position plainly:

> "a cancelled run is neither [completed nor flagged] ... a deliberate kill and an
> abandoned one are identical in accounting"

and everything else here works hard not to over-claim -- a Fisher exact test, a
Benjamini-Hochberg correction, Wilson intervals, `MIN_SAMPLES` -- before padding
the denominator with rows it had itself called uninformative.

Measured on a real 90-day history: **7.3% of placements are cancellations**, and
censoring them moves **7 of 9 rows**.

```
node             counted as successes    censored
midway3-0250     32/36   88.9%           32/33   97.0%
midway3-0330      9/73   12.3%            9/45   20.0%
midway3-0376     17/78   21.8%           17/64   26.6%
midway3-0025      1/12    8.3%           below MIN_SAMPLES
midway3-0116      0/12    0.0%           below MIN_SAMPLES
```

Two nodes falling below the threshold is the honest outcome when the informative
sample really is that small -- the tool already refuses to judge on thin evidence,
and inflating the denominator manufactures a confidence the data does not support.

**The hang metric keeps them, and that is not an inconsistency.** There a
cancellation is frequently the evidence itself: **340 of those 1,094** satisfy
`looks_like_noop` -- a job that held its allocation and computed nothing until
someone killed it. Dropping those would gut the metric that is the *default*. A
cancellation that did compute stays a trial there too: it ran, it did not hang,
and that is evidence. So `--nodes` with no flags is byte-identical, and only
`--metric failure` moves.

### The test that named the whole rate and pinned half of it

`test_cancelled_excluded_from_failure_rate` asserted `bad == 0` and nothing about
`trials`. Its own name says "the failure rate", which is a numerator over a
denominator; it held the numerator. With `bad` zero in that fixture the rate came
out the same either way, so it could never have caught this. It now asserts both.
Fifth instance in this record of a test that asserts less than its name claims.

### The negative result: everything else agrees

Seven marginal job shapes driven through all four consumers -- `patterns.usable`,
the workload grouping, `node_table` and `sizing.recommend`:

```
                 usable()  groups  node_tbl  sizing
open_ended         no        no       no       no
live RUNNING       no        no       no       no
no elapsed         no        no       no       no
zero elapsed       yes       yes      yes      no
no node            yes       yes      no       yes
cancelled          yes       yes      *        no
no steps           yes       yes      yes      yes
```

Every row is deliberate and consistent: an open record is unusable everywhere, a
job with no node cannot be attributed to one, and `sizing` alone declines
zero-elapsed and cancelled runs because it is the only consumer inferring a
*request* from them. The starred cell is this round's defect.

---

## Round twenty-five — "controlled for workload" was controlling on a name

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | The node comparison held a job *name* fixed, not a workload, so a multi-user query pooled different people's unrelated jobs into one stratum | `nodes.py` `dominant_workload`, `node_table` | `TestTheWorkloadControlHoldsOnePersonsWork` |

### 1. A confound the control did not control

`nodes.py` exists to answer "which nodes eat my jobs", and its whole method is
holding the workload fixed because placement is not random. It did that by
comparing normalised job **names**:

```python
records = [j for j in records if normalize_name(j.name) == normalize_name(workload)]
```

A multi-user query is one flag away -- `-u alice,bob` and `--all-users`, both in
the README's examples -- and on this cluster **25 job names are used by more than
one person** over two days: `interactive` by eight of them, `ssd_lab_base` by six,
`bc_jupyter` by four. Constructed from that shape:

```
alice: 12 runs of `interactive` on n1, all hung
bob:   12 runs of `interactive` on n1, all clean
alice: 12 runs of `interactive` on n2, all clean

before   n1  12/24   50.0%  worse     <- neither person's rate
after    n1  12/12  100.0%  worse     <- alice's, which is what was asked for
```

50% is a number belonging to nobody. `patterns.group_key` already puts the user in
the identity, for exactly this reason and in exactly these words -- "two people's
unrelated `run.sh` on one partition became a single fabricated workload" -- so the
codebase had already diagnosed the hazard and fixed it in one of the two places it
occurs.

`nodes.Workload` is that identity now: a name, an owner, and `matches()`.
`dominant_workload` counts by `(name, user)` and returns one; `node_table` filters
through it. Under the single-user query that is the default the user is constant
and nothing changes -- verified against a real 30-day history, byte for byte.

**It is a `str` subclass, and that was the second attempt.** A `NamedTuple` is a
tuple, so `"only %s counted" % workload` unpacks it and `workload in text` raises:
71 tests failed in one run. A value whose whole job is to be displayed should be
the thing displayed, so the class *is* its label and carries `.name` / `.user`
alongside. Every existing caller -- and the 47 test call sites that pass a bare
name -- keep working untouched, and a bare name still means "any user", which is
what it has always meant and is correct for a single-user history.

**The screen names the owner only where that is load-bearing.** `qualified` is set
when the history the workload was chosen from spans more than one user:

```
--all-users   controlled for workload: only dsafarian's oligomers counted
own history   controlled for workload: only rd-s#-run counted
```

**`--nodes --json` keeps a machine-readable field.** `workload` stays the bare
name, with the owner beside it in a new `workload_user`, rather than the display
label -- a consumer filtering on `workload` was reading a name and must keep
reading one.

### The negative results

* **`--all-users --nodes` at cluster scale**: 3 hours, ~80,000 jobs, 20.0s and
  514 MB. It runs, and its answer ("no node reached the 10 placements a comparison
  needs") is honest rather than wrong -- three hours of one workload is genuinely
  too thin. The defect was never that it failed; it was that the stratum it chose
  was not a workload.
* **453 distinct nodes** touched cluster-wide in two days, against the 3 the demo
  has and the 34 in a personal history. No layout or statistical problem at that
  scale.

---

## Round twenty-four — the shapes only a whole cluster has

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `slurmpast '49046820_[1-20%10]'` died: sacct prints that id and will not accept it | `sacct.py` `Sacct.jobs` | `TestAnUnexpandedArrayIdCanBeLookedUp` |
| 2 | A 123-character workload name with no spaces overran `--sizing` at every width and broke the workload title mid-name | `report.py`, `tui.py` | `TestAWorkloadNameWithNoSpacesInIt` |

### 1. An id sacct prints and then rejects

A pending array with a throttle is `49046820_[1-20%10]`. That is what sacct writes
in `JobID` under `--parsable2`, and what `squeue` shows -- so it is what anyone
copies. Handed back to sacct:

```
$ slurmpast '49046820_[1-20%10]'
slurmpast: sacct: fatal: Bad job array element specified: 49046820
```

Established against the live scheduler rather than reasoned about:

```
sacct -j '49046820_[1-20%10]'   fatal
sacct -j '49046820_[1-20]'      fatal      <- the brackets, not the %throttle
sacct -j 49046820               49046820_[1-20%10]|PENDING
sacct -j 49046820_4             accepted   (a real element)
sacct -j 53833807.batch         accepted   (a step id)
```

`queryable_job_id` reduces an unexpanded range to the master, which is the only
spelling sacct answers, and leaves every other form alone. The bracketed form does
not survive expansion, so there is no completed array to over-fetch.

Two real records now resolve that could not before, and both exercise round
eighteen's new findings on genuine data: a `DEADLINE` array reporting "Killed at
its --deadline, not its time limit", and a `NODE_FAIL` reporting "The node failed
under this job".

### 2. A name that `wrap` cannot break

`wrap` breaks at spaces. The longest job name on this cluster is 123 characters and
contains none:

```
nf-NFCORE_RNASEQ_RNASEQ_FASTQ_QC_TRIM_FILTER_SETSTRANDEDNESS_FASTQ_SUBSAMPLE_FQ_
SALMON_SALMON_INDEX_(genome.transcripts.fa)
```

`--sizing`'s workload header was **125 cells at 60, 74, 80, 100 and 120 columns** --
it wraps, and a single word comes back from the wrapper whole. The dashboard's
workload title did the same and Textual soft-wrapped it mid-name to column 0.

`report` documents this failure exactly, for a *detail value*: "a 68-character job
name is one word, so it came out of the wrapper unchanged and the row went to 89
cells on an 80-column terminal." It was fixed there with a clip and left in two
other places -- the sixth "fixed only on one side" in this record. So the rule is
named once now, `render.wrap_or_clip`, and `pair_value_lines` is expressed in terms
of it rather than repeating it.

The dashboard title is clipped rather than wrapped: it heads a one-line summary
that goes on to carry the counts, and wrapping it would push them onto a line of
their own. The counts themselves can still take that line past the width and
soft-wrap -- the overview's summary already does this with a long window string,
it is accepted behaviour on these screens, and the test says so rather than
quietly asserting less.

### The negative results

* **`expand_nodelist` on a real 264-character, 63-node allocation** --
  `midway3-[0002,0008,0012-0015,...]` -- expands and round-trips through
  `compress_nodelist` exactly. Round twelve fuzzed that over 4,000 synthetic
  hostlists; this is the first real one.
* **Every job-id shape the cluster produces** through `base_job_id`,
  `numeric_job_id` and `job_identifiers`: unexpanded arrays with and without a
  throttle, real elements, heterogeneous components, step ids, and the
  column-truncated `53601970_[0+`. No exception, and every one resolves to a
  sensible master.
* **The `_[0+` truncation is a display artifact, not a defect.** sacct's default
  column width truncates JobID exactly as it truncates `OUT_OF_ME+`; slurmpast
  queries with `--parsable2`, which does not. Checked because the two look alike
  and one of them *was* a defect.

---

## Round twenty-three — a hostname that was a sentence, and a table built twice

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `a` took 6.8s on a real history: every row of the job list was built twice | `tui.py` `OverviewScreen`, `JobListScreen` | `TestATableIsNotBuiltTwiceToOpenItOnce` |
| 2 | `NodeList=None assigned` -- sacct's "no nodes" sentinel -- was rendered as a node name with a count beside it | `sacct.py` `parse` | `TestTheNoNodesSentinelIsNotANodeName` |

### 1. 26,714 rows added for 13,363 jobs

Opening the flat job list on a real 30-day history:

```
width  before   after
   80   6.06s   3.13s
  100   7.11s   3.70s
  160   9.03s   4.79s
```

**None of it was slurmpast's arithmetic.** The cell values for all 13,363 rows --
every `cpu_utilization`, `cores_text`, `format_bytes`, `looks_like_noop` -- compute
in **0.32s**. `DataTable.add_row` was called 26,714 times: exactly twice per job.
`on_mount` populates the table and the first resize populates it again, with the
same layout and the same rows, because a screen pushed onto a laid-out app already
has its size.

`_rows_already_drawn` records the layout and a fingerprint of the row set and makes
the second call a no-op. The fingerprint is the job ids (or workload labels), built
fresh each call: microseconds against the seconds it saves, and unlike a cheaper
one it cannot miss a filter that changes the middle of a list while preserving its
length and its ends.

**Two wrong explanations, recorded because the method is the point.** The first was
that `on_mount` builds at `_DEFAULT_TABLE_WIDTH` before the screen has a size, so
the resize rebuilds at the real width -- and the trace written to confirm it printed
two builds at an identical layout, which is the opposite. The second was the fix
that followed from it: deferring the mount build to `call_after_refresh`. Measured
side by side, guard-plus-deferral is 3.64s and the guard alone is 3.55s, so the
deferral does nothing and is not in the tree. A first attempt at the guard itself
keyed on `id(rows)` and never fired at all, because every caller builds a fresh
list.

No overrun at 80, 100 or 160 columns on 930 real workloads, so the layout holds at
real scale; this was only ever latency.

### 2. A node called "None assigned"

sacct writes `None assigned` into `NodeList` for a job that never held an
allocation. 38 of the 15,085 carry it, every one CANCELLED at elapsed 0 --
cancelled while still pending. It was carried through as though it were a hostname:

```
nodes            None assigned  (1 node)
```

A node named "None assigned", and a count of 1 asserted about a job that got zero.

`expand_nodelist` already returned `[]` for it, so the node-reliability table was
never polluted -- verified, and now pinned. What leaked was the display and
`--json`'s `shape.node_list`, where a consumer would read it as a hostname.

Folded at the parse boundary, for the reason `_TRUNCATED_STATES` folds `OUT_OF_ME+`
there: that is where sacct's spellings stop being sacct's problem. Empty is what
the rest of the codebase already means by "no nodes", and `job_sections` omits the
row on a falsy `node_list`, so the contradiction disappears rather than being
papered over. `NNodes` is deliberately left alone: for a job cancelled while
pending it is what was *requested*, which is a real reading and the only one sacct
has.

No fixture in this suite had ever built the value. You have to have watched sacct
emit it to know it exists.

### The negative results

* **All 15,085 real post-mortems rendered**, checked for exceptions, overruns and
  leaked Python. No exceptions. The 89 overruns are all `workdir` and all declared
  `PATH_ROWS` -- deliberate, per its own comment: "a path you cannot copy whole is
  no use in a ticket". The "leaked `inf`" hits were the substring in
  `exp22-inference-serving`.
* **The finding distribution over a real history**, recorded because nothing had
  ever looked at it: `walltime-slack` 11,252, `memory-slack` 1,405, `cancelled`
  1,094, `system-cpu-heavy` 641, down to `command-not-found` 1. Every rule fires on
  real data and none of them floods it.

---

## Round twenty-two — the first round run against real data

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A rule whose docstring says "non-monotone walk" fired on requests that never moved, and rendered them unbounded | `patterns.py` `find_memory_search` | `TestAWalkThatDoesNotWalkIsNotASearch`, `TestTheMemoryWalkIsBounded` |

### 1. A search that never searched, printed 777 characters wide

`find_memory_search`'s docstring: *"Hand-bisection of `--mem`, visible as a
**non-monotone walk** across OOMs."* The code computes `monotone` and spends it
only on choosing between two *actions* -- it never tests that the walk moved. Over
90 days of this cluster's own history:

```
workload            OOMs  distinct  collapsed   rendered walk
caai-p#b_scan         71         1          1   777 characters
rd-r#-recon           16         1          1   172 characters
rc-tok-github_code     7         6          6    80 characters  <- an actual search
```

Two of three. The first rendered as ten screen lines of the same four characters:

```
[FAIL] Memory request is being hand-searched
       71 OOM kills for caai-p#b_scan with --mem walking 6.0 GiB -> 6.0 GiB ->
       6.0 GiB -> 6.0 GiB -> 6.0 GiB -> 6.0 GiB -> 6.0 GiB -> 6.0 GiB -> 6.0 GiB
       -> ... (seven more lines) ...
```

Both halves are wrong and both are fixed:

**The claim.** 71 OOMs at an unchanged request is not a hand-search; it is the same
request resubmitted 71 times. That is a real pattern and worth reporting -- it is a
*different* pattern. `memory-unchanged` now says so, with `memory-search` reserved
for a request that actually moved, following the `timeout-hang` / `timeout-real`
precedent of one rule, two shapes, two codes. The action follows: "Stop stepping"
is advice about a search, and there was none.

```
[FAIL] The same memory request keeps being OOM-killed
       71 OOM kills for caai-p#b_scan, every one of them at --mem 6.0 GiB: the
       request has not moved. Job 53363721_4 then COMPLETED at 6.0 GiB — a value
       that had already OOM'd.
```

**The rendering.** `_mem_walk` collapses consecutive repeats to `×N` -- a value
submitted twice is one step of a walk, not two -- and elides the middle past eight
steps, keeping both ends, because the first value is where the search started and
the last is what is being asked for now. Every other truncation in this codebase
announces itself; this one ran on instead. 777 characters becomes `6.0 GiB ×71`.
The cap is set so the longest genuine bisection in 90 days of real history (seven
collapsed steps) is never elided. `×` is in `_ASCII_FOLD` like every other mark.

Also corrected: `find_repeat_failures` pointed readers at "the memory-search
check", which is now one of two titles and neither of them on screen.

### The fixture the fix exposed

Two existing tests broke, and both were asserting more than they had evidence for.

`TestMemorySearchUsesTheRealLimit._series("48Gn")` set an explicit **per-node**
`ReqMem` of 48G on every row while `AllocTRES` varied 48 → 32 → 17 → 12. Slurm
cannot produce that record: `--mem=48G` allocates 48G. And `Job.mem_limit_bytes`
honours a per-node `ReqMem` over `AllocTRES` **by design**, documented at the
property -- so the fixture flattened all five requests to 48 GiB and the test had
been pinning "a search" over five identical values. It passed only because the
detector fired on any OOM series. The fixture now tracks the allocation, which is
what a real record does, and a guard asserts the series really varies.

Worth stating plainly, because the temptation was to "fix" `mem_limit_bytes`: it is
correct, the comment in `find_memory_search` that says "the limit comes from
AllocTRES first" is the imprecise one, and only the artificial fixture made them
look inconsistent.

`TestATruncatedStateMeansWhatItSays::test_the_cross_run_detectors_see_it` built
four identical records and pinned the code `memory-search`. Its subject is that the
truncated spelling `OUT_OF_ME+` is *visible* to the cross-run detectors at all;
which shape they name is beside that point, so it asserts the finding and its count
instead.

### The negative results from real data

* **Performance.** 15,085 jobs over 90 days: 11.0s end to end, 204 MB peak RSS.
  8.4s of that is the `sacct` subprocess and 2.7s is `parse()` over 36.5 MB;
  everything slurmpast then computes -- grouping 1,260 workloads, all patterns, the
  node table, sizing for every group -- is **1.0s together**. Nothing to optimise on
  our side of the subprocess.
* **The stale-record path, on a genuine stale record.** An 88-day `RUNNING` row that
  squeue has never heard of: correctly flagged, correctly excluded from totals, and
  correctly worded "squeue has never heard of it, so the job is long gone". That is
  round fifteen's `live` reaching real data.
* **Truncation tails** with 930 real workloads, including the case round five got
  wrong: `--sort name -n 3` reports "927 more workloads (13353 runs) holding 100.0%
  of the compute", which is correct -- the three alphabetically-first hold under an
  hour between them.
* Real post-mortems across FAILED, TIMEOUT and COMPLETED read correctly, including
  a TIMEOUT with 0.02s of CPU and 17.1 GiB of MaxRSS, where the report says the
  figure is not a footprint rather than sizing from it.

---

## Round twenty — the layout engine, and six rounds re-verified

Nothing found. Both halves are recorded in full, because a round that finds nothing
is only worth anything if the next one can tell what it actually looked at.

### The layout engine, as a property

`render.fit_columns` chooses which columns fit and how wide each gets. Four specs
in this codebase use it (`OVERVIEW_COLUMNS`, `JOB_COLUMNS`, `STEP_COLUMNS`,
`NODE_COLUMNS`) and those four were the whole of its coverage -- every width test
in the suite asserts about a *rendered view*, so the arithmetic was pinned by
example rather than by rule. Its docstring makes six promises. Over 40,000
generated specs:

```
a column is never narrower than its own header          holds
labels come back in display order, as a subsequence     holds
drop=0 is never dropped; lowest drop number goes first  holds
the table fits, or every survivor is undroppable        holds
fill_to is landed on exactly, or was already exceeded   holds
with no fill_to, a fixed column never grows             holds
```

The fourth is the `table_floor` case and the fifth needed care: 4,438 trials ended
wider than `fill_to`, which is correct -- `fill_to` spreads spare cells and never
shrinks -- and separating those from a real underfill is the whole difficulty of
asserting it. There were no real underfills.

### Six rounds re-verified against their own reproductions

Round six re-verified round five "by running each reproduction again, not by
reading the entries". Six rounds have now accumulated, and their tests could all
be green while the behaviour regressed underneath a shared helper. So all 34 were
re-run from a script that knows nothing about the test suite:

```
round 14   ? opens the help on all six screens                          6/6 ok
           title wraps at 68, gauged row fits 80, sentence keeps its half   ok
           arrow / CI cell / nodes heading identical on both surfaces       ok
           --ascii reaches the arrow; no ' -- ' left in any view            ok
round 15   workload banner carries the caveat; --json carries live          ok
           README and docs state the real JSON count                        ok
round 16   empty node grid hidden; "1 GPU-hour total, 1 of it never used"   ok
round 17   empty overview explains itself and hides its grid                ok
round 18   no sizing advice on any of the four interrupted states           ok
           exit 127 and 137 agree with the findings above them              ok
           BOOT_FAIL and DEADLINE each have a finding                       ok
round 19   patterns names the split; all-hung wording unchanged             ok

34 reproductions re-run, 0 still reproduce
```

### What this round says about the state of the codebase

Seven rounds, and the count runs **7, 3, 3, 1, 4, 1, 0**. The shape of what was
found changed with it: rounds fourteen to seventeen were about how things are
drawn, eighteen and nineteen about what the tool asserts, and twenty found nothing
in either. The three things every surface rests on are now pinned by properties
rather than examples -- `fit_columns` here, `sizing`'s never-advise-below-the-peak
invariant in nineteen, and `nodes`' statistics against scipy and statsmodels in
eighteen.

Released as **0.6.0** on that basis.

---

## Round nineteen — the same conclusion, qualified in one module and not the other

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | The patterns screen asserted "raising the limit will not help" of every timeout on the strength of half of them | `patterns.py` `find_repeat_failures` | `TestTheRepeatFailureActionNamesTheSplitToo` |

### 1. Four hangs speaking for four runs that were working

A workload of eight timeouts: four hung on 0.5 CPU-seconds, four burned 29:50 of a
30:00 limit doing real work. Three surfaces, on one screen:

```
workload banner (cross-run)
  → 4 of these consumed under 10 CPU-seconds — they hung rather than ran out of
    time. Raising the limit will not help; fix the blocking call.

open any of the other four (per-job)
  [FAIL] Ran out of wall clock while working
         Hit the 00:30:00 limit having used 07:46:40 of CPU (97.2%) — it was
         making progress.
       → Raise --time well above the limit that cut it off.
```

The banner sits directly above the rows those jobs are in.

**`sizing` had already found and fixed exactly this**, at the same
half-of-the-timeouts threshold, and its comment says why in the language this
round could not improve on:

> "The veto stands ... but it may not speak for every timeout in the group. The
> threshold is half, so four hangs among eight timeouts fired it, and 'These runs
> were blocked, not slow' was then asserted of the other four as well: runs that
> had burned 29:50 of a 30:00 limit doing real work. `looks_like_noop` needs CPU
> under 10s, so those are never hangs by this module's own definition. **Name the
> split, and keep what they proved.**"

`patterns.find_repeat_failures` draws the same conclusion from the same split and
did none of that. So the fix landed on the module a reader reaches through
`--sizing` and not on the one they reach through `p`, `--patterns`, or the banner
above every workload.

Fixed by sharing rather than copying -- the fifth time "fixed only on one side" has
been recorded here, so a sixth copy of the sentence was not the answer.
`hung_split_note` lives in `patterns` and `sizing` imports it, because `sizing`
already imports from `patterns` and the reverse would be a cycle:

```
mixed 4/4  → 4 of these consumed under 10 CPU-seconds — they hung rather than ran
             out of time. Raising the limit will not help those; fix the blocking
             call. The other 4 did compute, and were cut off at 00:30:00 — so once
             the blocking call is fixed, the limit has to be at least that.

all 8 hung → ... Raising the limit will not help; fix the blocking call.
```

"those" appears only where there is another group for it to exclude: at 14 of 14 it
qualifies nothing and reads as a hedge, so the demo's own wording -- and the
screenshots and the GIF cut from it -- are byte-identical.

### The negative result: `sizing`'s numbers, and the trap under them

The module header states an asymmetry: *"Over-requesting narrows which nodes can
host the job ... Under-requesting kills the run."* Every individual rule is tested;
the promise they exist to keep was not. 400 generated workloads with a planted peak
for walltime, memory and per-task cores:

```
569 actionable suggestions checked, 0 below what the workload needed
```

`--time`, `--mem` and `--cpus-per-task` all clear their measured peak, and a
`lower` verdict always lowers while a `raise` always raises. Pinned as a property
test.

**The trap, recorded because it is invisible and cost this round an hour.** The
first version of that check reported *thirteen* violations, all of them its own
fixture's. `Job.cpu_time` is

```python
max(cpu_time_alloc, elapsed * cpu_count, *[s.cpu_time for s in work_steps])
```

so a synthetic run built by `_replace`-ing three fields on a demo job keeps that
job's denominator in **two** places -- the allocation row and the step -- and every
utilization derived from it is wrong. Fourteen runs of differing length all
reported `cpu_time = 10956.0`. Build the rows and parse them; do not `_replace` a
real job. The property test asserts its own denominator before asserting anything
else, for that reason.

### Also checked, nothing found

* Every cross-run finding against every per-job finding it can co-occur with, over
  700 generated workloads: 21 pairs, one contradiction (above). `memory-search`
  against `host-oom` is the near miss -- "--mem is not the deciding variable"
  against "Raise --mem" -- but they cannot appear together, `sizing` already
  carries the caveat on its `--mem` advice, and giving a per-job rule its
  workload's history is a feature rather than a correction.
* No verdict disagreement between `sizing` and `patterns` on any split: wherever
  `patterns` says the limit will not help, `sizing` returns `unknown` rather than a
  number.

---

## Round eighteen — findings that argued with each other

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | Suppressing the noop finding on an interrupted run moved the wrong advice instead of removing it | `diagnose.py` `_cpu_rules`, `_gpu_rules` | `TestNoFindingContradictsTheOneAboveIt` |
| 2 | `BOOT_FAIL` and `DEADLINE` were in no rule at all, so a node that never booted was told to find its blocking call | `diagnose.py` `_exit_rules` | `TestTheTwoStatesDiagnoseHadNeverHeardOf` |
| 3 | "An exit status does not name a cause: exit 127 ..." printed under "A command in the script was not found (exit 127)" | `diagnose.py` `_exit_rules` | `TestTheExitCodeFindingsAgreeWithEachOther` |

### 1. A guard that made its own problem worse

`_cpu_rules` states the principle its guard exists for:

> "'Find the blocking call' is advice about the user's own code, and it is only
> honest when nothing else already explains the missing CPU time."

`_NOOP_ALREADY_EXPLAINED` held `OUT_OF_MEMORY`, `NODE_FAIL`, `PREEMPTED`, and the
comment beneath it records the fix as done: "Both are now suppressed there and
explained here."

They were not. The `return` sits on the branch that *fires*:

```python
if looks_like_noop(job) and job.base_state not in _NOOP_ALREADY_EXPLAINED:
    add(Finding(... "Allocation did essentially nothing" ...))
    return                      # <- only reached when the finding was ADDED
...
if util < LOW_CPU_UTIL and cores > 1:
    add(Finding(... "Most allocated cores were idle" ...))
```

So a suppressed state fell straight through to the next rule, and the reader got a
different piece of the same wrong advice:

```
[WARN] Most allocated cores were idle
       Utilization 1.0% of 16 cores, i.e. about 0.2 cores of real work.
       → Try --cpus-per-task=1, unless those cores feed dataloader workers.

[WARN] The node failed under this job
       Slurm ended this as NODE_FAIL ... a CPU or memory total near zero here is
       missing data, not a measurement.
```

An instruction computed from a number, two findings above the sentence saying the
number is not a measurement. The same on `PREEMPTED`, whose finding says "how far
it got says nothing about whether the job was healthy". `gpu-suspect-idle` infers
from the same `cpu_utilization` and did the same thing.

The guard now stops the whole function, is named `_CPU_TIME_ALREADY_EXPLAINED` for
what it governs, and covers all three rules. The *measured* GPU branch is
deliberately left outside it: `gres/gpuutil` is sampled while the job runs and says
what the cards did however the run ended -- only the CPU-based inference is
suppressed.

**`CANCELLED` is deliberately not in the set,** and the test says so: its finding
calls the *outcome* ambiguous, not the CPU total unreadable, so a cancelled run
that used one core of sixteen is still evidence about the request.

### 2. Two states `diagnose` had never heard of

`BOOT_FAIL` and `DEADLINE` are counted by `Job.failed`, graded "crit" by
`theme.STATE_HEALTH`, coloured red by `report._STATE_COLOR` and queried by
`--failed`. `diagnose.py` contained neither string. So the whole post-mortem for a
node that failed to boot was:

```
[FAIL] Allocation did essentially nothing
       00:30:00 of wall clock, 0.10s of CPU. Nothing was computed.
       → Find the blocking call. If this allocation is a deliberate reservation,
         mark it so and this rule will stay quiet.
```

-- the exact sentence the comment above says must only appear "when nothing else
already explains the missing CPU time", on a job where the scheduler has explained
it in the state field. And a *short* BOOT_FAIL, too brief for any rule to trip,
said **"nothing to flag"**.

Each now gets a finding of its own, in the same mould as the three beside it. This
is the one place in this round that adds rather than corrects, and the reason is
that suppression alone would have made the short case worse: BOOT_FAIL would have
gone from wrong to silent.

Severities follow their siblings, and they decide `slurmpast <jobid>`'s exit code:
`DEADLINE` is CRITICAL like both TIMEOUT findings (`model.py` already groups the
two -- "DEADLINE belongs here for the same reason TIMEOUT does"), `BOOT_FAIL` is a
WARNING like `NODE_FAIL`, because nothing the submitter did caused it.

### 3. A sentence that was true of exit 1 and false of the two codes the tool names

```
[FAIL] A command in the script was not found (exit 127)
       The shell could not locate an executable.

[WARN] Exited 127, but no log was found to explain it
       An exit status does not name a cause: exit 127 is indistinguishable from a
       CUDA OOM, a killed worker or a bad argument without the stderr text.
```

127 is the shell's "command not found" and 137 is 128+9; each has a rule a few
lines above that names it exactly. The generic sentence denies what the finding
directly above it just asserted.

This is the same self-contradiction the code's own comment records fixing *within*
one finding -- "a finding whose title said 'Exited 3' and whose evidence discussed
exit 1" -- reappearing between two, because that fix generalised the sentence
rather than asking whether it was still true.

The log is still worth asking for on these, so the finding stays and only its claim
changes:

```
[WARN] Exited 127, and no log to confirm it
       The status is named above. What it does not say is which command produced
       it or how far the run got, and that is in the stderr text.
       → Pass --log-dir, or set a predictable --error= path.
```

Exit 1 keeps its own more specific line, and every unnamed status keeps the generic
one, which is true of them.

### The negative result: the statistics

`nodes.py` implements a one-sided Fisher exact test, a Wilson score interval and
Benjamini-Hochberg by hand, because the analysis modules may not import a
third-party package. Nothing had ever checked them against a reference.

```
Fisher one-sided   5,986 comparisons vs scipy.stats.fisher_exact   max diff 7.7e-13
Wilson 95%        20,099 intervals   vs statsmodels proportion_confint  max diff 9.2e-06
Benjamini-Hochberg 3,000 families    vs statsmodels multipletests    0 disagreements
```

The Wilson gap is `Z = 1.96` against the exact normal quantile 1.959964 -- 0.001
percentage points on a figure printed to one decimal, and the constant is named and
commented. Not a defect. Recorded so nobody re-derives it.

---

## Round seventeen — a column header over nothing, twice more

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | The overview and job list drew a bare header when a filter or search matched nothing, and the overview suppressed the count that would explain it | `tui.py` `OverviewScreen`, `JobListScreen` | `TestATableThatMatchedNothingSaysSo` |

### 1. Two tables with no empty state, and a guard that hid the reason

Round sixteen's fix was to the node screen, whose empty branch needs a history
where nothing failed. These two need one keypress. Filter the overview to problems
on a week that went well:

```
before
  slurmpast — last 7 days  ·  failed, timed out, or idle
  last 7 days · 33 jobs in 6 workloads · 100.0% completed
  #     JOB NAME     PARTITION  RUNS  FLAGGED  CPU / GPU-HOURS  LAST RUN
  <nothing>
```

A column header over blank space, a count of 33 above it, and not one word about
the filter that emptied it. Search is the same, on both screens.

**And the overview could not say "showing 0".** That clause is guarded:

```python
if shown and shown != total_groups:      # <- `shown and`
```

Zero is falsy, so the one count that an empty table cannot speak for was the one
count suppressed -- while "showing 4" printed fine. The guard is now
`shown != total_groups`.

The wording is `render.nothing_matches`, shared so the two screens cannot explain
the same empty table differently, and it names both what narrowed and which key
undoes it:

```
after
  last 7 days · 33 jobs in 6 workloads · 100.0% completed · showing 0
    no workload matches the failed, timed out, or idle filter — f widens it.

  all jobs · 0 jobs · search: zzz
    no job matches the search "zzz" — escape clears it.
```

Both grids are hidden on that branch, as the node table now is. Checked that
`enter`, `f`, `s`, `/`, a digit, the arrows, `y`, `Y` and `?` all still work with
the grid hidden -- `on_mount` focuses that table, so this had to be verified rather
than assumed -- and that a table with rows still gets its grid and says nothing.

This is not a new principle. `PatternsScreen` has had it all along ("That is a real
answer, not an empty screen: these detectors stay silent rather than manufacture a
finding"), and `index.filter_jobs` writes the rule down in its own comment, about
the date search that was added *because a user hit it*:

> "Typing what you can plainly see and getting an empty list is the worst kind of
> empty result -- it reads as missing data."

Three of the four table surfaces now follow it. The fourth, `--plain`, never
reaches an empty table: `cli._load` raises `SacctError` and exits 2 with "no jobs
for &lt;user&gt; since &lt;window&gt;", which is the same answer in the shape a pipe takes.

### The negative results

Eleven degenerate histories -- empty, one job, one completed job, and one job each
with no name, no partition, no node list, no timestamps, no elapsed, no timelimit,
no steps, no TRES, and every field blank at once -- through all six plain renderers
and all seven screens at 90 columns. No exception, no width overrun, and one
finding, above.

Worth naming because it bounds the axis: after four rounds of cross-surface and
degenerate-input sweeps, the remaining defects are not in *whether* a view survives
its inputs. They are in what it says about them.

---

## Round sixteen — what a history of one job looks like

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | The nodes screen drew an empty grid under the sentence explaining there was nothing to show | `tui.py` `NodesScreen.refresh_rows` | `TestAnEmptyNodeTableIsNotDrawn` |
| 2 | "1 GPU-hours total, 1 of them never used" on the overview, both surfaces | `report.py:479`, `tui.py:932` | `TestOneGpuHourIsNotOneGpuHours` |
| 3 | Four more unguarded plurals round seven's sweep left behind | `index.py`, `patterns.py` x2, `tui.py` | `TestEveryCountedNounAgreesWithItsCount` |

### 1. The empty grid its own comment forbids

`NodesScreen.refresh_rows` carries this, immediately above the branch:

> `# Two ways this table has nothing to say, and an empty grid says neither.`

It then sets `rows = []` and leaves the `DataTable` mounted, so a history with no
bad outcome -- every run completed, which is the good case -- rendered:

```
node reliability — hang rate
  controlled for workload: only midtrain counted (placement is not random)
  baseline 0.0% over 14 placements
  No hangs recorded for midtrain in this window, so there is nothing to attribute
  to a node.
NODE                    N        RATE      95% CI          VERDICT
 no node is worse than the rest; nothing to exclude.
```

A bare header over nothing, which reads as a table that failed to load rather than
as a table with nothing in it -- and then a second sentence answering a question
the first has just said cannot be asked. `report.render_nodes` returns before
drawing any of it; the screen now does the same, with `table.display` and an empty
exclude note. Verified that `m`, `c`, `?` and `q` still work with the grid hidden
(`on_mount` focuses that table), and that a history *with* rows still gets both.

Worth naming precisely: `node_table` **does** return a row here. It is
`nodes_empty_reason` that says the row is not worth showing, which is why
`rows = []` beside a live widget was possible at all.

### 2. "1 GPU-hours total"

The overview's summary clause, written out in both front ends as
`"%.0f GPU-hours total"` and guarded in neither -- below the 25-character floor of
the sweep that catches duplicated sentences, exactly as round fourteen's arrow was.
One run of one card that hung is one GPU-hour, and it is the first thing anyone
tries:

```
before   1 job in 1 workload · 0.0% completed · 1 GPU-hours total, 1 of them never used
after    1 job in 1 workload · 0.0% completed · 1 GPU-hour total, 1 of it never used
```

Two disagreements in one clause. The pronoun is the subtler one: it refers back to
the **total**, not to the idle count, so one hour of which one was wasted is "1 of
it". `render.gpu_hours_total` and `idle_hours_note(idle, total)` now, shared.

### 3. Four the last plural sweep missed, and three it would have got wrong

Round seven fixed nine unguarded plurals. A rescan found twenty-one candidates;
**four are reachable and were reproduced by constructing the history**, and the
rest are guarded. Both halves matter -- a scan that reports a guarded site is a
scan nobody runs twice.

Reachable:

```
index.py:528    History.headline    1 GPU-hours, 1 of them in allocations that never computed
patterns.py:162 repeat failures     1 GPU-hours consumed by the failures.
patterns.py:366 noop summary        Together they held 1 GPU-hours.
tui.py:972,977  pasted overview row ... | 1 problems | ... | 1 GPU-hours | ...
```

Not reachable, checked rather than assumed:

* `diagnose.py:347` `"Utilization %s of %d cores"` -- the rule is gated on
  `cores > 1`, so "of 1 cores" cannot be printed.
* `render.held_back_note` and `nodes_correction_note` spell both forms out already
  (round seven fixed exactly these).
* `report.py:531` `"1 GPU-hour = %d CPU-hours"` -- the constant is 16.
* `patterns.py:147`, `nodes.py:537`, `render.py:703` -- each needs a sample size
  above 1 to fire at all.

The rule is `duration.plural(count, word)`, in `duration` rather than `render`
because three of the four sites are in `index` and `patterns`, which may not import
`render` -- it pulls in rich, and `CLAUDE.md` requires the analysis modules to stay
third-party-free. It agrees with the **printed digit**, not the float: 1.4 GPU-hours
renders as "1" through `%.0f` and takes the singular, the same "prints as" rule
`bar_cells` applies to a gauge.

### The negative result: `logs.py`

Opened for the first time in sixteen rounds and driven against a real filesystem
rather than read. Twelve documented behaviours, twelve correct:

```
slurm-<jid>.out found by name              StdOut pattern expanded and found
%x-%j in a logs/ subdirectory              SubmitLine -o expanded and found
job 60 does not claim 1060-train.out       --wrap's own -o is not an output path
array element finds the %A master file     --comment absolute path used
dangling .err skipped for the .out         --comment prose ignored
two jobs never handed the same file        a name match blocks a timing guess
```

Recorded so the next round spends its time elsewhere.

---

## Round fifteen — three surfaces, and the warnings only two of them carry

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | The dashboard printed sizing advice with the caveat that says when it is wrong stripped out | `tui.py` `WorkloadScreen.extra_summary` | `TestTheSizingCaveatReachesEverySurface` |
| 2 | `--json` could not say whether an open record was a live job or a dead one | `cli.py` `_job_json` | `TestTheJsonPayloadKeepsItsPromise` |
| 3 | The test the docs cite for (2) counts name mentions, and the docs' value count was wrong | `tests/test_audit.py`, `README.md`, `docs/details.md` | same class |

Minor: `--steps` was the only scoped flag whose `--help` line did not name its scope.

### 1. Advice with the safety note taken off

`sizing.Advice` carries a `caution` field, commented in the source as **"what would
make this advice wrong"**. Three surfaces render that advice. Only two render the
caveat:

```
--sizing          prints it, marked `!`, since it was added
--sizing --json   carries it, in `Advice._asdict()`
dashboard         never read the field at all
```

Six of the ten actionable recommendations the demo produces carry one:

```
cot-exp             --mem=3G           MaxRSS sums RSS across the process tree ... upper bound
cot-exp             --cpus-per-task=2  This is a GPU workload: cores may be there to feed
                                       dataloader workers, and cutting them can starve the GPU
att-speed-#         --mem=50G          MaxRSS ... upper bound
att-speed-#         --cpus-per-task=9  ... can starve the GPU
tokenize-shards     --mem=15G          MaxRSS ... upper bound
rc-tok-github_code  --mem=42G          the same request both failed and succeeded, so --mem is
                                       not the deciding variable
```

Side by side on `cot-exp`, before:

```
--sizing                              dashboard
  --mem  lower to 3G                    next run  --mem=3G          the most any run used ...
    the most any run used was 1.9 GiB.            --cpus-per-task=2  the busiest run used ...
    ! MaxRSS sums RSS across the
      process tree ... upper bound.
  --cpus-per-task  lower to 2
    the busiest run used 1.0 of 6.
    ! This is a GPU workload: cores
      may be there to feed dataloader
      workers, and cutting them can
      starve the GPU even though they
      look idle.
```

The GPU one is the reason this is first rather than last. The dashboard hands over
`--cpus-per-task=2` for a job holding a card, with the basis ("the busiest run used
1.0 of 6 cores per task") and without the sentence saying that reading is expected
and acting on it can starve the card. A reader of the app gets a *worse*
recommendation than a reader of the pipe, from the same measurement.

It is now under the basis, in the warning hue, wrapped to the terminal and
indented under the flag. Pointing at `slurmpast --sizing` for the reason was
already considered and rejected in this block's own comment -- "a bare number with
no basis, and for the reason a different command in a different program. The reason
belongs where the number is" -- so the caveat goes where the number is. The marker
is `render.CAUTION_MARK`, shared, for the reason round fourteen shared the arrow.

Costs the banner up to five lines on a cautioned workload. Checked at 60, 70, 74,
80, 100 and 140 columns: no overrun, and the table still gets thirteen rows on the
30-row terminal the screenshots are cut at.

### 2. `--json` could not tell a running job from a dead record

`cli._mark_open_records` asks squeue about anything unfinished and writes a
**tri-state** answer onto the job -- deliberately three values, per the model's own
comment: *"'no answer' and 'no such job' are different claims and only one of them
is a measurement."* Both text surfaces spend it on the finding's action sentence.
The JSON payload carried only `open_ended_record`, which is `true` in all three:

```
job.live     outcome.open_ended_record   the only thing that differed
---------    -------------------------   --------------------------------------------
True         true                        "squeue confirms it is still there ..."
False        true                        "squeue has never heard of it ..."
None         true                        "Confirm against squeue."
```

So the one consumer that cannot read English could not distinguish a job running
this second from one that died in March -- and `timing.elapsed_seconds` is measured
to *now* for both, which is precisely the artefact the distinction exists to flag.
Round six's headline defect was a queued array job reported as dead: the same
distinction, going the other way.

`outcome.live` now carries it, tri-state as stored.

### 3. The test the documentation points at

`docs/details.md` said, of that payload:

> Nothing is captured and then hidden; **a test fails if a field is read but never
> surfaced.**

`test_every_captured_field_is_exposed_somewhere` is the test it means. What it
asserts is that each annotated field name appears **more than twice** in the
concatenated text of `src/slurmpast/*.py`. `Job.live` appears four times -- once
declared, three times inside `diagnose` -- so it passed while being surfaced
nowhere a machine could read. The check cannot tell "rendered to a reader" from
"mentioned three times", and it never opens `_job_json` at all.

Kept, renamed `..._is_read_somewhere`, and its docstring now says what it is: a
catch for a field nothing reads at all, and nothing more.
`TestTheJsonPayloadKeepsItsPromise` is the real one -- it parses `_job_json`, collects every `job.x` and
`s.x` it reads, and holds every `Job` and `Step` value to that set. Thirteen job
values and three step values are exempt, **listed by name with what supersedes
each**, so the next one that is not emitted has to be argued for in the list rather
than dropped:

```
alloc_cpus, ncpus            -> shape.cpus          (Job.cpu_count falls back across them)
alloc_nodes, nnodes          -> shape.nodes
ntasks                       -> shape.tasks
total_cpu_alloc + 3 siblings -> cpu.total_seconds and friends
req_mem_bytes                -> memory.limit_bytes + memory.req_mem_raw
cores_busy, cpu_freq_hz      -> derived from emitted numbers
fs_disk_bytes                -> deprecated alias of filesystem.read_bytes
```

**And the count in the prose was wrong.** Both `README.md` and `docs/details.md`
said "174 values per job", pinned by nothing. It was never a property of a job: 174
is `95 job-level values + 2 steps x 40`, i.e. the floor over the demo, where the
real range is 174-189 depending on how many steps and findings a job has. Both now
read **"95 values per job, plus 40 for every step"**, and the same test computes
both figures from `_job_json` and fails if either drifts -- the guard the test badge
already has, after `tests-1029` sat stale in the README for two rounds.

### Minor: one flag that did not say where it applies

Four of the five scoped flags name their scope in `--help`; `--steps` did not.

```
--metric {failure,hang}   what --nodes measures (default: hang)
--all-workloads           skip the workload control in --nodes (confounded)
--sort ...                workload ordering (default: cost)
-n LIMIT                  rows in plain output
--steps                   per-step accounting              <- reaches one view, says nothing
```

Measured across twelve modes, `--steps` changes the output of exactly one:
`slurmpast <jobid> --plain`. It is accepted and silently ignored everywhere else,
including `--plain` over a list, which is the natural thing to try. Now reads
"per-step accounting, on a named job". No behaviour change -- `--json` has always
emitted steps unconditionally, and the dashboard's `y`/`Y` copy includes them.

---

## Round fourteen — one block, drawn twice, measured twice

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `?` opened the help on four screens of six and did nothing on the other two | `tui.py` `PatternsScreen`, `NodesScreen` | `TestTheHelpIsReachableFromEveryScreen` |
| 2 | The dashboard never wrapped a finding title, so it broke to column 1 | `tui.py` `JobScreen`/`PatternsScreen` | `TestTheDashboardWrapsEveryLineOfAFinding` |
| 3 | A gauged detail row overran by exactly the width of its own bar | `tui.py` `JobScreen.cell` | `TestAGaugedRowCountsItsOwnBar` |
| 4 | ...and clipped a sentence that `--plain` keeps whole | `tui.py` `JobScreen.cell` | `test_a_sentence_value_keeps_its_second_half` |
| 5 | The action arrow was `→` in the app and `->` in a pipe, and `--ascii` reached neither | `report.py:430,654`, `tui.py:1622,1701` | `TestTheFragmentsBothSurfacesDrawComeFromOnePlace` |
| 6 | Three more fragments written out twice: the CI cell, the severity tag, the nodes heading | `report.py`, `tui.py`, `render.py` | same class |
| 7 | Seventeen user-facing sentences spelled the em dash `--`, where the fold cannot reach it | `diagnose.py`, `patterns.py`, `sizing.py`, `sacct.py` | `TestTheProseSpellsPunctuationOneWay` |

Each was reproduced by running the code, and every fix was re-run against a
deliberately reverted tree to confirm its test fails without it.

### 1. The help documented a screen it could not be opened from

`HelpScreen` carries sixteen rows, and two of them are written for one screen in
particular:

```
("m", "on the nodes screen: measure hangs or failures"),
("c", "on the nodes screen: drop the workload control (confounded)"),
```

The nodes screen was one of the two that could not open it. Measured by pressing
`?` on each screen in turn:

```
overview      -> HelpScreen        opens
workload      -> HelpScreen        opens
job list      -> HelpScreen        opens
job           -> HelpScreen        opens
patterns      -> PatternsScreen    *** nothing ***
nodes         -> NodesScreen       *** nothing ***
```

The binding was written out on each screen that had it -- three copies of
`Binding("question_mark", "help", ...)` and three copies of a two-line
`action_help` -- which is exactly how two screens came to be without it. It moves
onto the mixin every screen already inherits, beside `y` and `Y`, so a new screen
gets it rather than remembering it. The mixin is `ScreenChrome` now, not
`ClipboardMixin`: it does two things and the name said one.

The round-eight test that should have caught this is the lesson.
`TestTheHelpScreenNamesEveryVisibleKey` iterates `tui.NodesScreen.BINDINGS` and
asserts the help documents each of them -- it walks past the nodes screen to check
the help mentions it, and never asks whether the reader can get there. Green
throughout. That is this suite's named failure mode, "tests that assert less than
they appear to", for the fourth round running.

### 2. The one line of three that nothing wrapped

Round seven wrapped the finding title in `report.py` and said why: "A title is a
sentence ... and this was the one line of the three going out at whatever length
it happened to be." The dashboard was not touched, so Textual soft-wrapped it
instead -- and a soft wrap restarts at column 0, which is the whole failure the
hard wrap exists to prevent. The job screen at 68 columns:

```
   WARN  Peak memory reads above the limit, yet nothing was
 OOM-killed
         32.5 GiB against a 32.0 GiB per-node limit, so it is not
         this job's footprint: MaxRSS sums RSS across the process
```

The evidence and the action below it hang correctly at column 8; the title's own
tail is at column 1, out from under the tag that introduces it. 61 cells is the
longest title `diagnose` produces, so this breaks below 74 columns and is fixed
above it.

`TestTheDashboardWrapsToTheTerminalItIsOn` measures exactly this widget and was
green, because it opens `cot-exp`, whose longest title is 47 cells. The title
that breaks is on the OOM jobs.

### 3. A row that did not count its own bar

`JobScreen.cell` budgeted a detail value at `4 + PAIR_LABEL_WIDTH + 1` -- the
indent and the label column. The row then drew a 14-cell bar and a 2-cell gap in
front of the value, and those 16 cells appeared in no sum anywhere:

```
80 columns, before:
     slowest task     ███████████▎░░  80.0% below average (task 3 on
 midway3-0372)

80 columns, after:
     slowest task     ███████████▎░░  80.0% below average (task 3 on
                                      midway3-0372)
```

81 cells on an 80-cell terminal. Not a narrow-terminal case -- the canonical one.
`report.py` had counted the bar since round five ("Continuation hangs past the bar
as well as the label"), and this is the same row of the same screen.

Both go through `render.pair_value_budget` now. Fitting it by clipping would have
been no fix: which task on which node is the entire content of the row.

### 4. ...and the same budget threw away half a sentence

The dashboard clipped an over-long value to one line; `--plain` wrapped it. Same
row, same job, two answers:

```
dashboard : utilization  not gathered by this cluster (needs AutoDetect=nvml in g…
--plain   : utilization  not gathered by this cluster (needs AutoDetect=nvml in
                         gres.conf)
```

`gres.conf` is the actionable half. Clipping is deliberate for a *path* -- "`p`
shows it in full, and --plain always does, because a path you cannot copy whole is
no use in a ticket" -- and `render.PATH_ROWS` exists to say which rows those are.
This one is not among them; it is prose, and prose wraps. `render.pair_value_lines`
now decides, for both surfaces, and keeps the path exemption verbatim.

### 5. Two arrows, and a flag that could reach neither

The action line of a finding was written out four times -- twice in `report.py`,
twice in `tui.py` -- and the two files had drifted:

```
tui.py:1622,1701   "→ " if index == 0 else "  "
report.py:430,654  "-> " if index == 0 else "   "
```

One element of one finding, two glyphs, and nothing on either screen from which a
reader could tell, because only one of the two is ever in front of them.

The expensive part is the second-order effect. `ascii_fold` maps Unicode
punctuation onto a one-cell ASCII stand-in, once, on the finished text of a plain
view, and `--ascii` exists to ask for that. The plain arrow was *already* ASCII, so
there was nothing to fold:

```
before   --patterns          ->  --mem is not the deciding variable: ...
         --patterns --ascii  ->  --mem is not the deciding variable: ...   (identical)

after    --patterns          →  --mem is not the deciding variable: ...
         --patterns --ascii  >  --mem is not the deciding variable: ...
```

That is round five's "two flags that were accepted and thrown away" and round
eight's `--ascii` finding, a third time, on the one glyph both of those rounds
looked straight at. `render.ACTION_ARROW` is two cells so the fold stays
one-cell-for-one-cell, which is what lets it run after the wrapping that measured
those cells.

### 6. Three more fragments written twice

`TestTheTwoSurfacesCannotDriftApart` (round seven) calls a literal prose at 25
characters and sweeps `report.py` against `tui.py` for duplicates. Everything
shorter is invisible to it, and that is where the rest of this round lives:

| fragment | `report.py` | the other copy |
|---|---|---|
| 95% CI cell | `"%.1f - %.1f%%"` | `tui.py` `"%.1f – %.1f%%"` |
| severity tag | `_SEV = {..., "FAIL"), ...}` | `render.severity_chip`'s own dict |
| nodes heading | `"node reliability (%s rate)"` | `tui.py` `"node reliability — %s rate"` |

Two of the three had already come apart. The CI column shows `75.7 - 100.0%` in a
pipe and `75.7 – 100.0%` in the app, for the same interval of the same row; the
heading over the same table reads two ways, and the parenthesis reads as an aside
where the metric is the subject. The severity tag agreed -- by luck, with two
hand-maintained copies of three words.

`render.ci_range`, `render.severity_tag` and `render.nodes_title` now. Under
`--ascii` the en dash folds back to the hyphen, so piped output is byte-identical
to what it always was.

### 7. One punctuation mark, two spellings

Seventeen user-facing sentences spelled the em dash `--` against thirty that
spelled it `—`, and `diagnose.py` did both inside one `Finding`:

```
diagnose.py:221  " Note MaxRSS reports %s against a %s per-node limit -- above ..."
diagnose.py:234  "Raise --mem, or cut what multiplies per-worker footprint — workers, ..."
```

An ASCII spelling is invisible to `ascii_fold`, so those sentences read the same in
both modes while everything around them changes -- and they cannot be restyled from
one place later. Counted over the non-docstring string constants of the fourteen
modules that render anything, which is the set that can reach a screen:

```
literals spelling it      before   after
  '—'                         30      47
  ' -- '                      17       0
```

Seventeen converted, thirty already right, and none of the seventeen had one
already. Rendering every demo view and every post-mortem afterwards finds no ` -- `
left on any surface.

Comments and docstrings are untouched and deliberately exempt: this repo writes
them in ASCII and none of them reaches a screen. The test scans non-docstring
string constants only, for that reason.

### The test gap this round found rather than fixed

`--steps` draws the fourth table in this codebase and no width test ever built it.
`TestPlainOutputFitsATerminal._views` builds five views and none of them passes
`show_steps`, and its sibling renders every demo job without it -- so three tables
are measured at six widths each and the fourth at none. It happens to behave: it
goes through `STEP_COLUMNS` like the others and bottoms out at its own floor of 67
(indented by four inside the post-mortem, not the two `table_floor` assumes). Pinned
now, so that stays a fact rather than a coincidence.

---

## Open (round fourteen)

**The memory walk keeps its ASCII arrow.** `patterns.py:235` joins the `--mem`
series with `" -> "`, and `docs/details.md:99` writes the same walk with `→`. Left
as it is, and named rather than silently kept: `ascii_fold` maps `→` to `>`, so
under `--ascii` the walk would read `32.0 GiB > 17.0 GiB` -- a comparison operator
in the middle of a sequence, and a false one in exactly the case the finding exists
to report, where the series moves both directions. The action arrow does not have
that problem because it sits at the start of a line where nothing can be read as
its left operand. The two are different things and now look different on purpose.

---

## Round thirteen — a search box that invited what it could not find

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | The overview's search promised job id, state and node, and matched none | `tui.py:448,470`, `index.py:344` | `TestTheSearchBoxPromisesWhatItMatches` |

### 1. Three descriptions, none of them right

One feature, described in three places:

```
tui.py:448   placeholder="filter by name, job id, state, node or date…"
tui.py:470   ("/", "search — name, job id, state or node"),
index.py:303 Search matches job id, name, state, partition, node list and timestamps
```

The placeholder omits partition, the help omits partition *and* date, and only the
docstring is complete — for the job list. The expensive part is that the same
placeholder appeared on the **overview**, whose search runs `filter_groups`, which
matches an entirely different set. Measured:

```
field          query                  job list       overview
job id         '5100001'              1 jobs         NO MATCH
name           'cot-exp'              20 jobs        1 groups
state          'TIMEOUT'              14 jobs        NO MATCH
partition      'test'                 58 jobs        8 groups
node           'midway3-0602'         8 jobs         NO MATCH
date           '07-01'                1 jobs         1 groups
```

Three of the five things the box invited, on the landing screen, returning nothing.
And `filter_jobs` already names this exact failure in its own comment, about the
date search that was added *because a user hit it*:

> "Typing what you can plainly see and getting an empty list is the worst kind of
> empty result -- it reads as missing data."

The two field sets genuinely differ and should: a workload rollup has no single job
id, state or node to match against. What was wrong was the invitation, so the
invitation is now derived from the behaviour. `index` names
`GROUP_SEARCH_FIELDS` and `JOB_SEARCH_FIELDS` beside the functions that use them,
`render.search_hint` turns either into English, and both the placeholder and the
help row are built from it:

```
job-list placeholder: filter by name, job id, state, partition, node or date…
overview placeholder: filter by name, partition or date…
help / row          : search — the overview matches name, partition or date;
                      a job list also matches job id, state or node
```

The help row is longer than the one it replaced and wraps to two lines inside the
box, which is only survivable because round eight taught that box to wrap -- checked
at 70 and 100 columns, no overrun.

**The other resolution, and why not.** The alternative is to make the overview
search its member jobs, so a job id or a node finds the workload containing it. That
is arguably what the placeholder's author intended, and it is a better feature. It
is also a behaviour change to the thing the request said not to change, and it costs
something real: `filter_groups` runs on every keystroke, and folding 6,574 jobs'
ids, states and node lists into a per-group haystack is materially more work than
the four short strings it joins today. Recorded rather than done; the escape hatch
already exists, since `a` opens the flat list where the full search works.

The test is behavioural rather than textual: for every field a screen advertises, a
real value of that field must return a non-empty result on that screen. Its control
asserts the three the overview cannot match are absent from its promise *and* still
return nothing — so the fix cannot be satisfied by quietly widening the promise
back.

### Consequence for the numbers

None. Two placeholders and one help row change; no measurement, no filter
behaviour, no exit code.

---

## Round twelve — a build step nobody could run, again

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `tools/demo_gif.py` imported two undeclared packages and said otherwise | `pyproject.toml`, `tools/demo_gif.py`, `README.md` | `TestTheToolsDeclareWhatTheyImport` |

### 1. The failure it was written to prevent

`tools/demo_gif.py` exists because the thing before it could not be run. Its
docstring says so:

> `assets/demo.tape` needs `vhs`, `ttyd` and `ffmpeg`, none of which are installable
> everywhere, and the result was that `assets/demo.gif` was *never committed at
> all* ... **A build step nobody can run is a build step that does not happen**, so
> this one uses what a dev install already brings in — Textual to drive the app,
> `cairosvg` to rasterize, Pillow to assemble.

It imports `cairosvg` and `PIL`. Neither was in `[dev]`, or in any other extra, or
in the core dependencies:

```
 dev = ['pytest>=7', 'pytest-asyncio>=0.23', 'pytest-cov>=4', 'ruff>=0.15,<0.17',
        'mypy>=2.3,<3', 'build>=1.0', 'twine>=5.0']
  cairosvg in dev extras: False
  pillow   in dev extras: False
```

So `pip install -e ".[dev]"` -- what all three CI jobs run, and what a contributor
reads as the setup step -- leaves `python tools/demo_gif.py` raising
`ModuleNotFoundError`. That is the tape's failure reproduced in Python: a build step
nobody can run, guarded by a sentence asserting they can. It only worked here
because this environment happens to carry both packages for unrelated reasons,
which is precisely the condition under which nobody notices.

Both imports are inside functions, so the failure was also a bare traceback with no
remedy in it -- in a repo whose CLI goes to some length to give "a one-line
explanation and exit 2, never a traceback".

Three changes, all small:

* a **separate `assets` extra** holding `cairosvg>=2.5` and `pillow>=9`. Separate
  from `dev` deliberately: cairosvg pulls a native cairo, and CI installs `[dev]`
  six times over -- four Python versions plus the oldest-Textual and coverage jobs
  -- without ever rendering a GIF. Putting it in `dev` would make every one of
  those builds carry a native dependency to do nothing.
* the docstring **corrected** to name the extra instead of claiming `dev` covers
  it, and the README's regenerate line changed to
  `pip install -e ".[assets]" && python tools/demo_gif.py`.
* both import sites now **report rather than raise**:

```
$ python tools/demo_gif.py          # with the two packages blocked
the GIF generator needs `pip install -e ".[assets]"` (pillow is missing)
$ echo $?
1
```

Verified both ways -- the generator still produces its 15-frame GIF, and with the
modules blocked it exits 1 with that line and no traceback.

The test walks every file in `tools/`, collects its non-stdlib non-local imports,
and fails on any that no dependency group declares -- with `PIL` mapped to the
`pillow` distribution, since the import name and the package name differ, which is
part of why this was easy to miss. Its control is `screenshots.py`, which genuinely
does run on a plain dev install: the sweep has to tell the two files apart rather
than flag both.

### Checked and found sound

* **`compress_nodelist` is a true inverse of `expand_nodelist`.** 18 hand-picked
  shapes plus 4,000 fuzzed hostlists across 11 prefix styles, mixed zero-pad widths,
  suffixed names, digitless names and disjoint runs: every one round-trips to the
  same set. The expansion side was differential-tested against `scontrol show
  hostnames` when it was written; the compression side had no such check and now
  has one measured.
* **The job-list table agrees across both surfaces** on all 58 rows and all 11
  shared columns. (Three attempts: two regex-based checkers gave false positives
  because STARTED and ENDED are single-space-separated and each value contains a
  space. The third compares alignment-independently -- every dashboard cell must
  appear in the plain row -- and finds nothing. Recorded because the first two
  "failures" were entirely mine.)
* **Nothing `goodput()` or `node_table()` computes is dead.** `gpu_noop_fraction`
  and the node table's `metric` are referenced exactly once each in the source,
  which reads as dead weight; both are emitted wholesale by `--json`
  (`"summary": history.stats`, and the node table dumped entire), so both reach a
  reader. Confirmed by running `--json` and looking, not by grepping.
* **`pyproject` metadata** otherwise checks out: the Textual floor matches CI's
  oldest-supported job, `rich` is declared rather than borrowed transitively, both
  console scripts resolve, and the classifiers match `requires-python`.

### Consequence for the numbers

None. Nothing in the app changed -- this round touched packaging metadata, one
tool's docstring and error handling, and one README line. `assets/demo.gif` was
regenerated as a by-product of verifying the generator still runs; it is
byte-equivalent in content to round eleven's.

---

## Round eleven — a gauge only one surface drew

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A gauged detail row drew its bar in the app and not in `--plain` | `report.py:269` | `TestAGaugedDetailRowIsDrawnOnBothSurfaces` |

### 1. `row[2]` was consumed nowhere in report.py

`render.job_sections` hands each detail row three values -- label, value, gauge --
and the plain renderer read the first two and stopped. `row[2]` appeared nowhere in
the module, so:

```
dashboard : slowest task     ███████████▎░░  80.0% below average (task 3 on midway3-0372)
--plain   : slowest task     80.0% below average (task 3 on midway3-0372)
```

The layout already knew about the gauge. `pair_rows`' own docstring says rows
"which carry a gauge still take a line to themselves", and that is why this row was
never paired -- so the plain renderer was reserving a full line for a bar it then
declined to draw. The three headline gauges in the same function are drawn here
already, via `resource_rows(..., flat=True)`; only the detail rows were skipped.

Exactly one row type carries a gauge, and the synthetic history has exactly one
multi-task job that produces it. That is why three consecutive rounds of width
sweeps, drift sweeps and prose sweeps went straight past it -- round six's "the
demo's own values are short", in its narrowest form yet: one row, on one job, in
one section.

Both surfaces now take the bar's width and gap from `render.DETAIL_BAR_WIDTH` and
`DETAIL_BAR_GAP` rather than the dashboard's own hardcoded `14`, the wrap budget
shrinks by what the bar costs, and a wrapped continuation hangs past the bar as
well as the label so the sentence stays under itself. Plain uses `flat=True` like
its three headline gauges -- whole cells, because an eighth-block tip with no
background reads as a notch -- so the two differ in tip precision and in nothing
else, which is the same difference `test_the_plain_report_uses_the_flat_bar`
already pins for the block above.

**The fix shipped broken and a test caught it.** The first version omitted
`ascii_mode`, so `--ascii` -- made good on only three rounds ago -- put `█` and `░`
straight back into output that had just been asserted pure ASCII.
`TestAsciiIsHonouredByEveryTextView` failed on the first run. Recorded because it is
the clearest evidence in this file that the tests from earlier rounds are doing
work, rather than merely accumulating.

### Checked and found sound

Four sweeps that turned up nothing, so the next round can skip them:

* **60 random key sessions, 40 keypresses each** -- 2,400 presses over the full
  binding set including `escape`, `q`, digits, `/`, `w`, `r`, `M` and the modal
  keys, at five terminal widths and three heights. No crash, no unhandled
  exception.
* **`fit_columns` holds its contract** for all four specs at every `available`
  from 10 to 260 and both padding values: it never exceeds the width it was given
  unless the never-dropped columns cannot fit -- which is the documented
  `table_floor` behaviour -- and `fill_to` lands on exactly the requested total
  rather than short.
* **The job post-mortem agrees field for field across both surfaces** on seven
  jobs spanning TIMEOUT, OUT_OF_MEMORY, FAILED, CANCELLED and three clean runs:
  every shared label carries the same value, and the row sets are identical. The
  gauge above was the single disagreement, and it was found this way rather than by
  reading.
* **The parse fuzzer is quiet again.** The same 5,500-case sweep that found round
  ten's NaN and OverflowError now completes with zero failures.

### Consequence for the numbers

None. One row of `--plain <jobid>` gains a 14-cell bar in front of a percentage it
already printed; nothing else moves. `assets/screenshot-job.svg` and
`assets/demo.gif` are regenerated, though the screenshot's job is single-task and
so unaffected by this change -- they were rebuilt to keep the whole set current with
the tree rather than because this round staled them.

---

## Round ten — a NaN that spread, and a test that looked away

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | One unreadable record turned a whole history's totals into `nan`, then raised | `duration.py`, `sacct.py` | `TestOneBadRecordCannotPoisonTheRest`, `TestAValueThatIsNotANumberIsNotAMeasurement` |
| 2 | `1 jobs in 1 workload` on both overview surfaces | `report.py:422`, `tui.py:814` | `TestSingularPlural` |
| 3 | The package docstring named 6 of the 10 third-party-free modules | `__init__.py` | `test_the_package_docstring_lists_every_module_the_guarantee_covers` |
| 4 | `Constraints` called "field 32 of 107" -- two different denominators | `sacct.py:38` | — (comment only) |

### 1. A value that is not a number is not a measurement

Found by fuzzing `parse()` with malformed rows, which is how it should have been
found: nothing here is reachable by reading the happy path.

`float("NaN")` and `float("1e999")` are floats Python builds happily, and three of
the four parsers let them through or died on them:

```
NaN     parse_duration -> nan      parse_bytes -> None                   _int -> None
inf     parse_duration -> inf      parse_bytes -> RAISED OverflowError   _int -> RAISED OverflowError
1e999   parse_duration -> inf      parse_bytes -> RAISED OverflowError   _int -> RAISED OverflowError
```

Only `parse_cpu_freq` was safe, and by accident -- its plausible-clock range check
rejects a NaN because every comparison with one is False.

`OverflowError` is not a `ValueError`, so `except ValueError` in `sacct._int` and
`duration.parse_bytes` did not catch it: one `inf` in `Priority`, `ReqCPUS`,
`NNodes` or any byte field took the **entire query** down with a traceback. Trap 9
at the top of `sacct.py` is the rule that breaks -- "a wedged accounting database
must not wedge the tool".

The NaN is worse, because it does not stay where it started:

```
=== healthy only ===
  stats total    : 4.0 | core-hours 8.0
  job screen     : rendered

=== healthy + one NaN Elapsed ===
  elapsed values : [3600.0, nan]
  stats total    : nan | core-hours nan
  job screen RAISED: ValueError: cannot convert float NaN to integer
```

One unreadable record and the healthy job's 4.0 GPU-hours is gone from the total,
which now reads `nan`. That is the exact failure `duration.py`'s opening rule was
written against -- "Each must yield None, never 0.0 -- a 0.0 here silently becomes
'this job used no time', which is a lie" -- except a NaN tells the lie about every
job at once, and then the job screen refuses to render at all. Seven of the fifteen
formatter-by-value combinations raised; the rest printed `nan%`, `inf TiB` and
`-infs`.

Closed at the parse boundary, which is where this module already handles sentinels:
every parser returns None for a non-finite result, `_int` catches `OverflowError`,
and every formatter renders one as the absent value rather than raising. The control
asserts the guard rejects nothing finite -- including the `0` and the negative that
other rules here deliberately allow through.

### 2. The test navigated away from the screen it was named for

```
--- --plain overview ---
    1 jobs in 1 workload · 100.0% completed
--- dashboard ---
    OverviewScreen : w  ·  1 jobs in 1 workload  ·  100.0% completed
    JobListScreen  : all jobs  ·  1 job    <- what the test reads
```

`%d jobs in %d workload%s`: the second count was guarded and the first was not, in
one sentence, on the landing screen, in both front ends.

`TestSingularPlural.test_one_job_is_not_reported_as_one_jobs` exists for precisely
this. It presses `a` first -- which leaves the overview for the job list, whose
sentence is a different one and was always correct -- and then asserts. Its sibling
`test_one_workload_is_not_one_workloads` reads the overview and checks the
`workload` half of the very same line, so the only half that was broken was the
only half never looked at. Both screens are read now, and the plain renderer has
its own check because it builds the sentence separately.

Round seven fixed nine of these and this one survived, which is worth saying
plainly: that round swept for the `"" if n == 1 else "s"` idiom being *absent*, and
here it was present -- on the wrong count.

### 3. A guarantee wider than the sentence promising it

`__init__.py` said the analysis modules are "``sacct``, ``diagnose``, ``patterns``,
``nodes``, ``index``, ``site``". `CLAUDE.md` and
`test_the_analysis_layer_needs_no_third_party_package` both hold ten to that rule;
the four unnamed were `model`, `sizing`, `logs` and `duration`. `sizing` is the
module the README's own library example imports, so a reader checking whether it
was safe on a login node was told nothing about it. Now derived from the same
static read the enforcing test uses, so the list cannot fall behind again -- with
a control asserting it does not over-claim one of the four renderers either.

### 4. Two denominators in one clause

`Constraints` is "field 32 of 107 here". It is field 32 of the **85** this module
asks for; 107 is what Slurm offers. The number that matters for the sentence -- a
pipe shifts every column after it -- is the position in the requested list, so a
reader who went and counted Slurm's 107 would land somewhere else.

### Checked and found sound

Worth recording, because a round that only lists what it broke reads as if it
looked nowhere else:

* **The three surfaces agree on every overview number.** Runs, completed, flagged
  and last-seen compared row by row across `--overview`, `--overview --json` and
  the dashboard's DataTable: no mismatches.
* **All six sort modes agree** across the library, the text view and the JSON, and
  the dashboard's `s` cycle walks `SORTS` in order and wraps.
* **The self-describing numbers are right**: `table_floor(JOB_COLUMNS)` is 74 and
  `NODE_COLUMNS` 41, exactly as `render.table_floor` claims, and `_FIELDS` is 85.
* **The TUI has no overrun** at 80, 100 or 120 columns on any of eight screens,
  driven with a 68-character workload name, a 45-character node name and a
  40-character partition.

### Consequence for the numbers

For a history whose fields all parse, nothing changes. For one containing a value
that is not finite, the change is large and in the right direction: that record now
reports `n/a` instead of `nan`, every other record's totals survive it, and the job
screen renders instead of raising. `--plain` and the dashboard both say "1 job"
where they said "1 jobs".

---

## Round nine — the demo's clock, and a state that meant two things

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | Every synthetic job's `End` contradicted its own `Elapsed` | `demo.py:112` | `TestTheDemoClockAgreesWithItself` |
| 2 | `OUT_OF_ME+` was recognised in one module and mis-handled by six | `sacct.py:188` | `TestATruncatedStateMeansWhatItSays` |
| 3 | `Submit` equalled `Start` while `Reserved` claimed a one-second wait | `demo.py:113` | `test_submit_is_before_start_by_the_queue_wait_it_reports` |

### 1. A demo of something Slurm cannot produce

`_job` wrote `End="2026-07-%02dT23:59:00"` -- a flat end-of-day stamp, whatever the
job actually did. So on the job screen:

```
  ● TIME   ██████████████████       101.4%   · 00:30:26 of the 00:30:00 limit
  ...
  timing
    submitted        2026-07-19T03:54:00             started          2026-07-19T03:54:00
    ended            2026-07-19T23:59:00             queued for       1.0s
```

Twenty hours and five minutes between the two timestamps, three rows under a gauge
saying the job ran thirty minutes and was killed for it. All 58 records were like
this; measured by parsing the demo and differencing:

```
timestamp inconsistencies: 58
    ('elapsed != end-start', '5100001', 'cot-exp', 1826.0, 86340.0)
```

`demo.py`'s own docstring is the standard it fails: "Nobody should be able to
mistake a demo screenshot for a measurement." A screenshot nobody can mistake for
a measurement is not the same as one that contradicts itself, and this is the
second kind. `_time_of_day` two functions above states the general rule -- "a demo
whose clock disagrees with its ids is a demo of something Slurm cannot produce" --
which round five wrote while fixing the *submission* clock and never applied to
`End`.

`End` is now `Start + Elapsed`, and a 42-hour allocation is allowed to cross
midnight rather than being clamped back into its own day. The control asserts
exactly that, because clamping is the wrong fix that would satisfy the main test.

**The wrong timestamp was published.** `assets/screenshot-job.svg` carried the
`23:59` and the README displays it. Both it and `assets/demo.gif` are regenerated
from `tools/screenshots.py` and `tools/demo_gif.py`; the job frame now reads
`started 03:54:00 / ended 04:24:26`, which is the 00:30:26 the gauge claims. Two
of the five SVGs changed and three came back byte-identical, which is the
generator being deterministic rather than three being skipped.

### 2. One spelling, two meanings

sacct cuts a state name to the column width and marks it with `+`, so
`OUT_OF_MEMORY` can read `OUT_OF_ME+`. The codebase knew that in exactly one
place: `_TERMINAL_STATES` listed it, and it appeared nowhere else in `src/`,
`tests/` or `docs/`. Run the parser on one and the record is correctly treated as
closed and then mis-handled by everything after:

```
OUT_OF_MEMORY  failed=True   findings=['host-oom']  memory-search=True   mem advice=raise
OUT_OF_ME+     failed=False  findings=[]            memory-search=False  mem advice=unknown
```

So a cgroup OOM kill counted as neither a failure nor a completion -- out of
`GroupStats.failed`, out of `problems`, out of `fail_rate`'s denominator -- drew no
`host-oom` finding, and was invisible to both the memory-bisection detector and the
`--mem` floor in `sizing.memory_advice`. That is the same shape as `Job.failed`
omitting DEADLINE, which round three fixed and `model.py` still explains.

Folded at the parse boundary now, which is where `_ALIASES` already undoes a field
Slurm renamed, and the truncated entry is gone from `_TERMINAL_STATES` because it
no longer reaches it. The `by <uid>` suffix survives the fold -- `Job.state` carries
it and `base_state` drops it, and both are read.

**Stated plainly:** this tool queries with `--parsable2`, which does not truncate,
so the spelling does not arrive from its own query. It arrives from a replayed or
injected runner, which `Sacct(runner=...)` exists to support. The entry was in the
codebase already; the defect is that one spelling of one state meant two different
things in one codebase, and that is worth closing whichever query produced it.

### 3. A queue wait the timestamps denied

`Reserved="00:00:01"` while `Submit` and `Start` were the same string, so the job
screen read "submitted 03:54:00, started 03:54:00, queued for 1.0s" -- three rows,
two of which contradict the third. `Submit` is now one second before `Start`, from
the same named constant that writes `Reserved`.

### Considered and not changed

**Job ids ascend while dates jump backwards between series.** Real, and measured:
four boundaries, e.g. 5100020 is 2026-07-20 and 5100021 is 2026-07-05. Slurm hands
out ids in submission order, so this is the same invariant `_time_of_day` names.
Left alone: no screen shows both sides of a boundary, so nothing contradicts itself
on screen, and fixing it means re-dating the whole synthetic history -- which
changes the LAST RUN column, the workload ordering, and every committed asset.
That is a rewrite of the demo narrative, not polish. Recorded here so the next
round does not have to re-find it.

**`REVOKED` and `SPECIAL_EXIT` are graded by nothing.** Both are terminal states
this parser accepts, and `theme.STATE_HEALTH` has no entry for either, so they
render with no judgement. For REVOKED that is right. For SPECIAL_EXIT it is a
judgement call the repo has not made, and making one silently is what the **Open**
section below exists to prevent.

### Consequence for the numbers

`--demo` changes: every synthetic `End` and `Submit` moves, so the ENDED column and
the timing rows differ, and the two regenerated assets with them. No real
measurement changes.

For a real history, one thing can: a record whose State arrives truncated as
`OUT_OF_ME+` now counts as a failure, draws `host-oom`, and feeds the memory
detectors -- so `slurmpast <jobid>` on such a record exits 1 where it exited 0, and
a workload holding them can gain a `memory-search` finding and a `--mem` floor it
did not have. On any history whose states are spelled in full, nothing moves.

---

## Round eight — the flag and the screen that half-worked

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `--ascii` changed nothing in five of the six plain views | `cli.py`, `report.py` | `TestAsciiIsHonouredByEveryTextView` |
| 2 | The help box overran its own frame, and the terminal below 80 columns | `tui.py` `HelpScreen` | `TestTheHelpScreenIsWrappedLikeEveryOtherScreen` |
| 3 | A long job name overran `--plain` where the dashboard clipped it | `report.py:262` | `TestALongValueIsCutTheSameWayOnBothSurfaces` |
| 4 | `p` meant something else on a job screen; `m` and `c` were in no help at all | `tui.py` `_HELP_KEYS` | `TestTheHelpScreenNamesEveryVisibleKey` |

### 1. A flag accepted and thrown away, for the third time

```
$ diff <(slurmpast --demo --overview) <(slurmpast --demo --ascii --overview)
$ echo $?
0
```

Byte-identical, and the same for `--plain`, `--patterns`, `--nodes` and `--sizing`.
`cli.main` passed `ascii_mode` to `render_job` and to `tui.run` and to nothing
else, so five of the six plain renderers never learned the flag had been given.
That is round five's #7 and #8 -- "Two flags that were accepted and thrown away" --
recurring on a third.

Underneath it a second, narrower thing: even in `render_job`, which *did* receive
the flag, `ascii_mode` only ever reached `render.bar` and `render.health_dot`. So a
terminal that could not draw `●` got the ASCII fallback for that and then an em
dash and a middle dot anyway:

```
$ slurmpast --demo --ascii 5100019 | grep -c '[^ -~]'
2
```

Both halves are closed by one shared `render.ascii_fold`, applied once per view to
its finished text -- the flag has to reach the sentences as well as the glyphs, and
the sentences are assembled in a dozen places.

Every substitution is deliberately **one cell for one cell** (`—`→`-`, `·`→`|`,
`…`→`.`, `→`→`>`), because the fold runs after wrapping and after `clip` has
reserved its marker cell; a two-character replacement would push a row that had
just been measured to fit back over the width it fits. A test asserts every line
keeps its exact length through the fold.

Not applied to the dashboard, and the help now says so rather than promising more
than the flag can do: Textual draws the frame in box characters whatever we pass,
so folding our prose there would buy a reader nothing they could see. `--plain` is
the surface that gets piped somewhere with an opinion about encoding.

The control is the one that matters: a fold applied to nothing would satisfy
"output is pure ASCII" on any view that was already ASCII. So the flag is asserted
to change a view **exactly when** that view had something to fold -- stated as an
equivalence, because `--patterns` on the demo history genuinely holds no foldable
character and demanding a difference there would pin the fixture rather than the
flag.

### 2. The screen that explains the app was the one nobody wrapped

Rounds five, six and seven each wrapped the prose on some surface and wrote down
why. `HelpScreen` was on none of their lists, and it had all three symptoms at
once. Its box is `width: 78` with a round border and `padding: 1 2`, so the content
gets 72 cells:

```
 75    a              every job in one flat list, ignoring the workload grouping  <-- OVERFLOWS by 3
 74    Y              copy the whole view (a job screen copies the full report)   <-- OVERFLOWS by 2
```

Textual soft-wrapped both and dropped the continuation at column 2, out from under
the description it continues -- "the orphan at column 0 that `_prose_width` exists
to prevent", on the screen that documents `_prose_width`'s own keys:

```
│    a              every job in one flat list, ignoring the workload        │
│  grouping                                                                  │
```

A third line was worse, because its length is not ours to know: the clip path is
interpolated from `_clip_path()`, so it is 78 cells on the machine this was found
on and unbounded in general. That is round six's folded-workload-name trap
("the demo's own values are short") in a new place. It now gets its own line, so
the sentence around it always reads whole, and the path itself is the same
deliberate overrun `report.py` already accepts for one -- "a path you cannot copy
whole is no use in a ticket".

And `width: 78` is a floor as well as a ceiling in Textual, so below an 80-column
terminal the box was drawn wider than the screen and simply cut, with no marker:

```
### terminal 70
    │    n              which nodes your jobs fail on, controlled for work
```

No right border, no `…`, nothing saying the line had been cut -- the one thing
`render.clip` exists to prevent. The box is now measured, less `_SCROLLBAR` for the
reason `_text_width` gives (the help is taller than a short terminal, so the modal
grows a scrollbar and a box sized to the full width loses its border to it), and
rebuilt on resize. Above 80 columns the cap binds first and nothing changed.

### 3. The same row, cut two ways

`report.py` wraps a solitary detail value to a budget, and `wrap` breaks at spaces.
A job name has none:

```
--- PLAIN (COLUMNS=80) ---
  len=89      name             nemotron-batch-h200-tokenize-shards-stage3-retry-17-experimental-arm
--- DASHBOARD (80) ---
  len=79       name             nemotron-batch-h200-tokenize-shards-stage3-retry-17-expe…
```

The dashboard had always clipped it -- `JobScreen.cell` calls `_clip` for anything
`render.PATH_ROWS` does not declare a path -- so the two surfaces disagreed about
the same row of the same screen, and the one meant for pasting was the wrong one.
Both now go through `render.clip`, so a cut cell says it was cut.

`PATH_ROWS` keeps its exemption and a test says so: `workdir` still overruns on
purpose, because `--plain` exists to be pasted.

### 4. A key that meant two things, and two keys that were documented nowhere

`HelpScreen` is reachable from the job screen, and from there it said:

```
p              what keeps failing the same way, across runs
```

`JobScreen` binds `p` to `toggle_paths`, `show=False`. So a reader on that screen
got neither the patterns screen the help promised nor any hint in the footer of
what they had actually done. The row names both meanings now.

`m` and `c` are the only two bindings shown in a footer -- the nodes screen's --
and absent from the help entirely, and `c` undoes the workload control the `n` line
directly above advertises. Both added. A test walks every screen's `BINDINGS` and
fails on any `show=True` key the help does not mention, so the next one cannot slip
through either.

### A test of round seven's, narrowed

Round seven added an AST sweep banning a hand-computed width in any `render.wrap`
call in `tui.py`. It matched on `max(...)`, which is too blunt: `HelpScreen` clamps
its own already-measured box width that way, legitimately. It now bans deriving the
width from `size.width` at the call site, which is what `_prose_width` exists to do
once and correctly -- and it carries a control asserting the sweep still recognises
the exact spelling it was written to ban, since narrowing a sweep is the change
most likely to leave it matching nothing.

### Considered and not changed

**The dashboard's prose is still Unicode under `--ascii`.** Deliberate, argued
above, and now said in `--help` rather than left as a silent shortfall.

**`_clip_path()` creates a directory as a side effect of rendering the help.**
Real, and left: it is `exist_ok=True`, it is pre-existing, and changing when a
cache directory appears is a behaviour change this round was not asked for.

**`PatternsScreen` exposes no `Text` attribute for tests** the way `NodesScreen`
does, so its assertion reads the compositor instead. Noted rather than fixed --
adding one is a change to a screen that works.

### Consequence for the numbers

None. `--ascii` output changes, which is the point; without the flag every view is
byte-identical, and a test pins that every line keeps its exact length through the
fold. Nothing else moves a measurement, a threshold, an exit code or a sort order.

---

## Round seven — polish

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | Two front ends drew the same sentence and had already drifted | `report.py`, `tui.py` | `TestTheTwoSurfacesCannotDriftApart` |
| 2 | `1 nodes were tested` | `render.py:669` | `test_the_note_pluralises_the_table_size_too` |
| 3 | `after correcting for 1 tested` | `report.py:684`, `tui.py:1715` | `test_the_exclude_header_names_the_noun_at_one_node_too` |
| 4 | `1 allocations ran over 00:05:00` | `patterns.py:355` | `test_one_idle_allocation_is_not_one_allocations` |
| 5 | `1 were killed within 15 minutes, so those were` | `patterns.py:364` | `test_one_quick_kill_is_not_one_were_killed` |
| 6 | `1 were FAILED` | `patterns.py:147` | `test_a_dominant_state_of_one_is_not_one_were` |
| 7 | `1 further groups show` | `patterns.py:197` | `test_one_hidden_repeat_group_is_not_one_groups` |
| 8 | `The other 1 did compute, and were cut off` | `sizing.py:201` | `test_one_computing_timeout_is_not_were_cut_off` |
| 9 | `over 1 placements`, `1 seen, all below it` | `render.py:604,643` | `test_one_placement_is_not_one_placements` |
| 10 | `test · 1 runs`, `1 of 1 jobs failed`, `1 more workloads (1 runs)` | `report.py:763`, `index.py:502,518` | three in `TestEveryCountIsSpelledForItsNumber` |
| 11 | The node screen guessed its chrome instead of measuring it | `tui.py:1734,1748` | `TestTheNodeScreenMeasuresItsChromeRatherThanGuessing` |
| 12 | One `--help` example's description sat a column left of the other eight | `cli.py:29` | `TestTheHelpExamplesLineUp` |
| 13 | `StdOut`/`StdErr` dated to Slurm 21.08 in three places, 24.05 in two | `model.py`, `cli.py`, `docs/details.md` | `TestTheStdOutBoundaryIsOneNumber` |

### 1. A sentence written twice is a sentence that will differ

`CLAUDE.md`: "`render.py` exists so the dashboard and `--plain` cannot drift. A
change to one surface that the other also draws belongs in `render.py`, not in
both." Three sentences had been moved there and given a docstring each saying why
(`nodes_baseline`, `nodes_empty_reason`, `held_back_note`). Seven had not:

```
$ python - <<'EOF'    # prose literals present in both files, docstrings excluded
... shared prose literals between report.py and tui.py: 7
EOF
  report.py:[700]  tui.py:[1733]  '%d further node%s scored worse too, left off the line: ...'
  report.py:[607]  tui.py:[1641]  '(placement is not random)'
  report.py:[403]  tui.py:[740]   ', %.0f of them never used'
  report.py:[608]  tui.py:[1642]  'controlled for workload: only %s counted %s'
  report.py:[572]  tui.py:[1549]  'no cross-run pattern met its evidence threshold.'
  report.py:[707]  tui.py:[1741]  'no node is worse than the rest; nothing to exclude.'
  report.py:[684]  tui.py:[1715]  'worse than every other node, after correcting for %d tested:'
```

An eighth was in the same block and did **not** appear in that list, because the
two copies were no longer the same string:

```
report.py:692  "not applied for you — excluding nodes trades availability for reliability.",
tui.py:1723    "not applied for you — excluding nodes trades availability for "
tui.py:1724    "reliability, and that is your call.",
```

One sentence, one block of one view, two texts. It is invisible from either side:
whichever surface you are looking at renders exactly one of them.

All eight now come from `render.py`. The shorter wording is what survived --
"not applied for you" has already said whose call it is, which is the same trim
this file records three times over for other lines. `WORKLOAD_CONTROL_ASIDE` is
exported rather than buried because both surfaces emphasise it separately from
the rest of its sentence.

Two tests, because the two halves fail independently: an AST sweep asserting no
prose literal appears in both modules, and a rendering check on each front end
asserting the shared string is what actually reaches the screen. The sweep alone
would pass if both surfaces stopped drawing the sentence.

### 2-10. Nine counts that read wrong at one

Everything in this codebase carries the `"" if n == 1 else "s"` idiom, and round
six's `TestCountsAreSpelledForTheirNumber` pinned two instances of it -- then
stopped. Nine more were reachable, one of them printed by `--demo` itself:

```
$ slurmpast --demo --nodes
  worse than every other node, after correcting for 1 tested:
```

`held_back_note` is the sharpest of the nine, because the same sentence
pluralises its other count correctly and not this one:

```python
>>> held_back_note(1, 1)
'1 interval clears the baseline on its own — but about one in twenty does that by
 chance and 1 nodes were tested, so on its own that is not yet evidence.'
```

The rest, each reproduced by running the code that emits it:

```
1 allocations ran over 00:05:00 while consuming under 10 CPU-seconds.
2 allocations ran over 00:05:00 ... 1 were killed within 15 minutes, so those were already noticed
5 of 5 runs of w in test failed; 1 were FAILED.
1 further groups show the same repeat-failure pattern
The other 1 did compute, and were cut off at 00:30:00
baseline 100.0% over 1 placements; 1 node below threshold omitted
No node reached the 10 placements a comparison needs — 1 seen, all below it.
w  test · 1 runs
1 of 1 jobs failed  /  1 jobs, nothing flagged
1 more workloads (1 runs) holding 50.0% of the compute
```

Two are worth naming beyond the missing "s". `1 were FAILED` needs five failures
across five distinct states to reach, which is the least likely of the nine and
the only one that changes a verb rather than a noun. And "1 seen, all below it"
is not fixed by pluralisation at all -- "all" is the wrong quantifier for one --
so it reads "1 seen, and it is below it" now.

Every control asserts the plural spelling is untouched: a fix that simply deleted
the "s" would otherwise pass.

### 11. The module that had been burned by this guessed anyway

`tui._prose_width` exists because "screen width minus a constant" is wrong, and
its docstring spends nine lines on the measurement:  "``#body`` is 96 wide inside
a 100-cell screen. Two cells is enough: a finding wrapped to 90 was drawn at
8 + 90 = 98, Textual soft-wrapped the overflow, and the reader got ... the orphan
at column 0 that ``_prose_width`` exists to prevent, surviving inside it because
the chrome was guessed rather than read."

Two `render.wrap` calls on the node screen were still spelling the guess out:

```
screen=100  _text_width=98 | _prose_width(2)=96 vs size.width-6=94 | _prose_width(4)=94 vs size.width-8=92
```

Consistently two cells narrow, at every terminal size, because the constants
double-count the scrollbar `_text_width` has already taken off. The direction is
safe -- these two lines wrapped early rather than overrunning -- which is why
nothing caught them, and it is still two sentences wrapping differently from
every other sentence on their own screen. The test is an AST sweep: no
`render.wrap` in `tui.py` may take a hand-computed `max(...)` width.

### 12. One space

`RawDescriptionHelpFormatter` prints the epilog literally, so the alignment is
whatever the string says:

```
 35  '  slurmpast                        dashboard over the last 7 days'
 34  '  slurmpast -S now-30days         ... over the last 30 days'
 35  '  slurmpast 51170455               post-mortem for one job'
```

Invisible in the source, plain on screen. Pinned by measuring the column every
example's description starts at and asserting there is one of them.

### 13. A version boundary the code had already researched

`logs.py` opens with the boundary table and is explicit about the trap:

> 1. **StdOut/StdErr, from Slurm 24.05.** Absent in 20.11, 21.08, 22.05, 23.02 and
>    23.11; present in 24.05. (21.08 is the release that added ``SubmitLine`` and
>    ``AccountingStoreFlags=job_script`` -- not these fields.)

`sacct.py` agrees ("SubmitLine from 21.08, StdOut/StdErr only from 24.05"), and so
does `report.py`. Three other places said 21.08 anyway -- `model.py`'s field
comment, `cli.py`'s JSON comment, and the compatibility table in
`docs/details.md`, which is the one a reader consults to find out what works on
the Slurm they have. Five releases were being told they have a field they do not.

The test anchors on the code rather than grepping for the number, because 21.08 is
the *right* answer three lines away in the same files -- `render.py`'s "submitted
as" row is dated from `SubmitLine`, correctly, and a sweep over the bare version
would have demanded that be broken too. It has its own control saying so.

### Documentation

**README's Textual range.** It read "Textual 0.89–8.2" against a `pyproject` pin
of `textual>=0.86,<9` and a CI job named `oldest-textual` that installs
`textual==0.86.*`. The floor was understated by three releases. Now read out of
the pin by a test that also checks the CI job installs the same number, so the
three cannot part again.

**Test badge.** 1195 → 1221, which `test_the_test_badge_matches_the_suite`
already enforces.

### Considered and not changed

**The job table overruns a terminal narrower than 74 columns.** Real, and already
recorded: `render.table_floor` computes it per spec, `report.PLAIN_MIN_WIDTH`'s
comment says it is "a floor on the *layout*, NOT a promise that every view fits 60
cells", and `TestPlainOutputFitsATerminal` asserts against the floor rather than a
constant. Not a defect, by the codebase's own account of it.

**`--demo` still ignores `-S` and `-E`.** The standing **Open** entry below. Left
alone, and not re-litigated.

**The dashboard's patterns screen adds a paragraph the plain report does not**
("That is a real answer, not an empty screen ..."). The shared *sentence* now comes
from `render`; the extra paragraph stays, because vertical room is exactly the kind
of thing that legitimately differs between a dashboard and a pipe -- the same
argument `nodes_empty_reason` makes for taking `widen` as a parameter.

**`--json` on the list branch computes a per-job severity and then discards it.**
Traced and left: the text branch on the same path does the same thing deliberately,
and the comment above it says so. Changing it would move behaviour, which this
round was asked not to do.

### Consequence for the numbers

None. Nothing here changes a measurement, a threshold, an exit code or a sort
order. Thirteen fixes, all of them wording, wrapping, alignment or a comment --
the widest-reaching is that eight sentences now have one home instead of two, and
they render byte-identically on both surfaces except the one that had drifted,
where `--plain`'s spelling won.

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

**Round twenty-seven.** A job whose log merely mentions NCCL loses its
`nccl` finding, and with it a CRITICAL -- so `slurmpast <jobid>` can exit 0 where
it exited 1, on a job whose only CRITICAL was the invented one. A job with a real
fault is unchanged, as is every job with no log. Nothing else moves, and the demo
writes no logs at all.

**Round twenty-six.** `slurmpast --nodes --metric failure` reports different rates:
a cancellation is no longer a trial, so denominators shrink and rates rise -- on a
real history 7 of 9 rows moved and two nodes dropped below `MIN_SAMPLES`. A node
that was `worse` can stay `worse` at a higher rate, and a node with few
non-cancelled placements can vanish from the table. `--nodes` with no flags is the
hang metric and is **unchanged**, as is the demo and every committed asset.
`note_for_allocation` on the job screen uses the failure metric and moves with it.

**Round twenty-five.** This one moves a measurement, but only on a query that spans
users. `--all-users --nodes` and `-u alice,bob --nodes` now compare one person's
workload rather than everyone's jobs that share its name, so a rate can change --
50.0% to 100.0% on the constructed pair above. A single-user query, which is the
default, is byte-identical. `--nodes --json` gains `workload_user`; `workload`
itself still carries the bare name. The screens name the owner only when the
history spans users.

**Round twenty-four.** `slurmpast <unexpanded array id>` starts working where it
exited 2; nothing that worked before changes, since every other id form is passed
through untouched. A workload name too long to wrap is now clipped with `…` in the
`--sizing` header and the dashboard's workload title, where it used to overrun.
No measurement, no verdict, no exit code, and the demo is unaffected.

**Round twenty-three.** `shape.node_list` in `--json` becomes `""` instead of
`"None assigned"` for a job that never held an allocation, and the post-mortem drops
the `nodes` row for those jobs rather than inventing one. Nothing else changes on
screen; the table fix is latency only, and the demo is unaffected either way.

**Round twenty-two.** A finding changes its code, title and wording where a
workload's `--mem` never moved: `memory-search` becomes `memory-unchanged`, which a
`--json` consumer filtering on the code will see. The walk in the evidence of a
genuine search is collapsed (`32.0 GiB ×2` for what was `32.0 GiB -> 32.0 GiB`) and
elided past eight steps -- so the demo's own patterns output, its screenshot and the
GIF all change. No measurement, no verdict, no exit code.

**Round twenty.** Nothing changes. Two tests were added and no source file was
touched.

**Round nineteen.** One sentence, on one branch: a `repeat-failure` finding whose
workload mixes hung and computing timeouts gains the split clause and the word
"those". A workload where every timeout hung -- which is what the demo has, and
what most real ones have -- is unchanged word for word, so the assets are
byte-identical. No measurement, no verdict, no exit code, no JSON field.

**Round eighteen.** This one moves an exit code. `slurmpast <jobid>` on a
**BOOT_FAIL** now exits 0 where it exited 1: its only finding used to be a CRITICAL
`noop-allocation` and is now a WARNING `boot-failed`, matching `NODE_FAIL`, which
has always exited 0. **DEADLINE** is unchanged at 1, by way of a CRITICAL finding
that names the deadline instead of one that blamed the script. Any CI step keying
off that code sees the BOOT_FAIL change.

Beyond that: four `NODE_FAIL`/`PREEMPTED`/`BOOT_FAIL`/`DEADLINE` post-mortems lose
the `cpu-overrequest` and `gpu-suspect-idle` findings entirely -- deliberately,
they were computed from a figure the same report calls missing data -- and the
`exit-nonzero-nolog` title and evidence change for exit 127, exit 137 and signal 9.
No measurement moves, and `--json` gains no field.

**Round seventeen.** Presentation only, and only on a branch that previously showed
nothing: two screens gain a sentence where a filter or search matches nothing, the
overview's summary gains "showing 0" where it printed no clause at all, and two
grids are hidden when they have no rows. Nothing changes on a table with rows,
which is why the committed assets are byte-identical.

**Round sixteen.** Presentation only; no measurement, no exit code, no JSON field.
Six sentences change wording where a count is 1 -- the overview summary, the footer
headline, two pattern findings and two cells of the pasted overview row -- and the
nodes screen stops drawing a table on the branch where it has no rows. Nothing
changes on a history large enough for any count to exceed 1, which is why the demo
and the committed assets are byte-identical.

**Round fifteen.** One addition and one correction that a consumer may be reading.
`--json` gains `outcome.live` per job, so a payload is 95 job-level values where it
was 94 -- additive, nothing renamed or removed. The documented totals in `README.md`
and `docs/details.md` change with it, and are now pinned by a test. On screen, the
workload screen's banner grows by up to five lines where a recommendation carries a
caveat; no measurement or exit code moves.

**Round fourteen.** No measurement changes and no exit code moves; every fix is
presentation. Three things a reader or a script might be matching on do change in
`--plain`, all of them in the Unicode form only -- under `--ascii` the output is
byte-identical to what it was:

```
                   before                       after        --ascii
action arrow       "        -> "                "        → "  "        > "
95% CI cell        "75.7 - 100.0%"              "75.7 – 100.0%"  "75.7 - 100.0%"
nodes heading      "node reliability (hang rate)"  "node reliability — hang rate"
```

Seventeen sentences also swap ` -- ` for ` — `, which shortens each by one cell.
Anything grepping the plain output for those literals should pass `--ascii`, which
is what that flag is for, or match the `--json` field instead.

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
