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

> **Release 0.8.0, 2026-08-24.** Twenty-one defects, every one filed by someone
> else running the published 0.7.0 against a cluster this package had never seen --
> midway2: CentOS 7.9, Python 3.14.6, Slurm 23.02, cgroup v1, no `C.UTF-8`, no
> per-job `cpuacct`, and compute nodes with no passwd entry for the user. 1560
> tests at 0.7.0, **1753** here; all four gates clean.
>
> What a user gets that they did not have at 0.7.0: a post-mortem that shows the
> job rather than a phantom built from its own `--wrap` script; a redirect that
> writes a report instead of 26 KB of escape sequences and then hanging; output at
> all under a non-UTF-8 locale, where every text mode used to emit zero bytes; a
> requeued job that says it was requeued, with the time its abandoned attempts
> burned; a CPU figure that admits it cannot see a detached worker pool, instead of
> telling a job using its eight cores to ask for one; `--sizing` advice that a
> partition can actually schedule; a log behind someone else's mode-700 home
> reported as unreadable rather than deleted; and three modes that no longer
> traceback when `sbatch --export=NONE` leaves no identity behind.
>
> Six of the twenty-one were narrowed or answered rather than adopted, and each
> says so where it sits: the anchored JobID regex the report asked for deletes live
> pending-array rows on this cluster; `--plain --json` is not a conflict; `-n`
> stays on the `--json` path because it bounds per-job work rather than rows; a
> partition is not named as a replacement because `sinfo` cannot say who may submit
> to it; the `--patterns` requeue rule waited for data to set its threshold; and a
> 100% baseline is only called a workload failure once there are enough placements
> to support the claim.

> **Release 0.8.1, 2026-08-24.** Three defects, all found by running the published
> 0.8.0 against a **third** cluster: Mercury, at the University of Chicago Booth
> School of Business -- RHEL 9.8, Slurm 25.11.3, cgroup v2,
> `jobacct_gather/cgroup`, 120 sacct fields, system Python 3.9. 1753 tests at
> 0.8.0, **1766** here; all four gates clean.
>
> Two properties of that cluster did the work. It is the first slurmpast has run
> on where MaxRSS comes from the cgroup rather than the process tree, and the
> first whose slurmdbd has outlived a job-id counter reset.
>
> What a user gets that they did not have at 0.8.0: `slurmpast <jobid>` no longer
> invents a requeue out of a stranger's seven-year-old job on a cluster that has
> recycled its ids -- it did that on all 40 ids sampled there, and no window
> suppressed it -- while a genuine requeue, array elements included, still
> reports. The per-job memory advice now says what MaxRSS means *on the cluster it
> is running on*, instead of contradicting `--sizing` about the same figure in the
> same run. And any figure between 1 KiB and 1 MiB renders as KiB rather than as a
> raw byte count beside a GiB in the same column.
>
> Nothing was withdrawn this round.

> **Release 0.8.2, 2026-08-25.** Five defects, found by running the working tree
> against **two** clusters at once and re-checking a third after every fix: Mercury
> (RHEL 9.7, Slurm 25.11.3, Python 3.13.15), **Pythia** (RHEL 8.10, Slurm 24.11.5,
> Python 3.12.14) and midway3 (Slurm 20.11.8, Python 3.11.14). A five-year Slurm
> span, three interpreters, both `jobacct_gather` plugins. 1766 tests at 0.8.1,
> **1842** here; all four gates clean on all three.
>
> The round's first finding is about the suite itself: **it could not run on either
> new cluster.** A plain `python3.12 -m venv` plus `pip install -e ".[dev]"` gave
> 1821 passed / 2 failed on both, because two tests build an sdist in-process and
> Python 3.12 stopped seeding `setuptools` into new venvs. Neither midway3 nor CI
> could see it -- conda seeds `setuptools`, and `ci.yml` installs it by hand before
> the test extra -- so the first environment to install the package the way the
> README describes was the first to fail.
>
> What a user gets that they did not have at 0.8.1: one workload called one thing,
> where the overview table named a 20-run group
> `m110_robustness_current_source_20260823_c9ea44e_v1` and the cross-run finding
> directly beneath it called the same group `m#_robustness_current_source_#_c#ea#e_v#`;
> a job that sent its output to `/dev/null` told the output was discarded rather than
> that its log had been *moved or deleted*, which was 5.7% of the records on Pythia;
> the dashboard and `--plain` describing a missed log the same way, where the app said
> only "none found" and `--plain` named the path and the reason; and a `--partition`
> that does not exist at this site named as the filter that emptied the window,
> instead of the window being called empty while holding 18 jobs.
>
> Nothing was withdrawn. Four things were checked and are not defects, each recorded
> with its reasoning: a 101-run workload at zero completed and zero flagged (all
> cancelled), a `--all-users --nodes` timeout on midway3, exit 2 on a cluster where
> the caller has no jobs, and an NFS that forces mode 0700 on the clipboard file.


> **Round thirty-five, 2026-08-25.** Five defects, found by running the working
> tree against **two** clusters at once and holding a third fixed: Mercury
> (RHEL 9.7, Slurm 25.11.3, Python 3.13.15) and **Pythia** (RHEL 8.10, Slurm
> 24.11.5, Python 3.12.14), with midway3 (Slurm 20.11.8, Python 3.11.14) re-run
> after every fix to check nothing regressed there. A five-year Slurm span, three
> interpreters, two `jobacct_gather` plugins. 1823 tests before, **1842 after**;
> all four gates clean on all three.
>
> The round's own method is the finding worth recording first: **the suite could
> not run on either new cluster.** `python3.12 -m venv` plus
> `pip install -e ".[dev]"` gave 1821 passed / 2 failed on both, because since
> Python 3.12 `venv` no longer seeds `setuptools` and two tests build an sdist
> *in-process*. midway3 passed 1823 only because conda happens to seed it. That is
> this package's own portability claim -- somebody on another cluster runs the
> shipped suite -- failing for a reason that is not about the package.
>
> What a user gets that they did not have at 0.8.1: one workload is called one
> thing, where the overview table said
> `m110_robustness_current_source_20260823_c9ea44e_v1` and the cross-run finding
> below it said `m#_robustness_current_source_#_c#ea#e_v#` about the same 20 runs;
> a job that sent its output to `/dev/null` is told the output was discarded
> rather than that its log was *moved or deleted*, on 5.7% of the records on
> Pythia; the dashboard and `--plain` describe a missed log the same way, where the
> app said "none found" and `--plain` named the path and its reason; and a
> `--partition` that does not exist at this site is named as the filter that
> emptied the window instead of the window being called empty.
>
> Nothing was withdrawn. Four things were checked and are **not** defects, listed
> in the round below: a 101-run workload at zero completed and zero flagged, a
> `--all-users --nodes` timeout on midway3, exit 2 on a cluster where the caller
> has no jobs, and an NFS that forces mode 0700 on the clipboard file.


> **Round thirty-four, 2026-08-24.** Three defects, found on a **third** cluster:
> Mercury (UChicago Booth) -- RHEL 9.8, **Slurm 25.11.3**, cgroup v2,
> `jobacct_gather/cgroup`, 120 sacct fields, system Python 3.9. 1753 tests before,
> **1766 after**; all four gates clean.
>
> The cluster mattered twice over. It is the first one this package has run on
> where MaxRSS is gathered from the cgroup rather than the process tree -- the arm
> §1k of this file records as never having been exercised -- and it is the first
> whose slurmdbd has outlived a job-id counter reset.
>
> That reset produced the round's worst finding: `sacct -D -j <id>` carries no
> window, so it answered with every job that had ever held the id, and
> `_fold_incarnations` keyed on the id alone. All 40 ids sampled from three recent
> days came back with a second row from 2019 belonging to a **different user**, and
> every per-job view on that cluster reported `requeued 1x` -- attributing a
> stranger's job to the reader as their own job's history. Windowed queries were
> never affected; `-S/-E` filters those rows out at sacct, and only the per-job
> path, which has no window to pass, ever saw them. Passing `-S` explicitly did not
> help.
>
> The cgroup arm found the second: the `memory-slack` finding hardcoded "MaxRSS
> over-reports multi-process jobs", which is true under `jobacct_gather/linux` and
> false here. `site.maxrss_caveat()` exists precisely so this is asked of the
> cluster, and `diagnose` already used it for the two findings immediately above --
> this one was missed, so a single run printed both readings of the same figure.
>
> What a user gets: no invented requeue history on a cluster that recycles job ids,
> one answer rather than two about what MaxRSS means, and sub-megabyte figures in
> KiB instead of raw bytes beside GiB in the same column.
>
> Nothing was withdrawn. One of the three tests written for the id fix passed
> against the deliberately broken tree on the first attempt -- `parse` keys
> allocations on `(JobID, Submit)`, so two same-instant rows collapse before the
> fold ever sees them -- and it was rewritten with distinct timestamps until the
> mutation caught it.


> **Round thirty-three, 2026-08-22.** Four defects, none of them found here: the
> published 0.7.0 was installed on **midway2** -- CentOS 7.9, Python 3.14.6, Slurm
> 23.02, cgroup v1, no GPU -- and run against that cluster's real history. 1560
> tests before, **1581 after**; all four gates clean.
>
> A `sacct` field containing a newline shattered the record, so 41 real rows parsed
> as 56 "jobs" and the overview reported 47 unterminated records where there were
> 2 -- and, worse than its own report first said, `slurmpast <jobid>` on any job
> submitted with a multi-line `--wrap` rendered a *phantom* instead of the job,
> reporting "the record was never closed" about a job that had OOMed four minutes
> earlier. `slurmpast > report.txt` launched the dashboard anyway and hung until killed,
> having written 26 KB of escape sequences into the file. And the internal grouping
> signature was being printed as a workload's name, so a date-stamped job appeared
> in the top 25 as `#`.
>
> Two parts of the report were narrowed rather than adopted, and say so: the
> suggested delimiter-counting reassembly is wrong for the field that triggers the
> bug, and the predicted cluster-wide merge of all-numeric names is bounded by
> `group_key` already keying on user and partition.

> **Round thirty-two, 2026-08-22.** No defect in the product -- and one in the
> audit itself, caught not by any of this round's four probes but by CI, on the
> job four local gates cannot see. 1560 tests; green on Textual 0.86 **and** 8.2.8,
> which is the first time this branch has been run against the floor.
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

> **Round thirty-seven, 2026-08-26 — a polish pass, no defects.** No behaviour
> changes and nothing filed; the parser's hot path was measured and tightened.
> 1882 tests at round thirty-six, **1917** here; all four gates clean.
>
> Where a 30-day window on one user actually goes (43,643 rows, 31.5 MB of
> `sacct` output): **subprocess 7.41 s, parse 2.66 s, index 0.34 s.** The
> `sacct` share is the accounting database's own time and is not ours to
> shorten -- trimming the 80 requested fields does cut it (7.14 s to 2.87 s for
> ten fields), but every one of them feeds `--json`, whose contract is
> documented as emitting everything, so that is not a polish change.
>
> The Python half was worth 22%. `parse.get` -- one call per field per row,
> **1,975,028 of them** -- lowercased its `name` argument on every call and then
> handed the same string to `_clean`, which lowercased it again to test
> `_FREE_TEXT`: **7,095,157 `str.lower()` calls** to recompute a property of 85
> compile-time constants. Each name is now resolved once per parse into
> `(column, is_free_text)`, and `_clean` is inlined at that one site (it remains
> the shared implementation for `_int`, `_seconds` and the `sstat` parser, which
> are not hot). 2.71 s -> 2.18 s. Two smaller ones took it to **2.10 s**: a
> precompiled regex for `_looks_like_job_id`, which was walking every character
> of every line through a Python generator 305,931 times, and a leading-digit
> pre-filter on the sentinel test. End-to-end load 10.41 s -> 9.76 s.
>
> **Two equivalences are pinned by test rather than assumed**, because both
> speedups rest on them. `re.search(r"\s", v)` replaces
> `any(ch.isspace() for ch in v)` in the guard that stops SP-1, so the two are
> checked against each other over **all 1,114,112 Unicode code points** (0
> disagreements) plus every JobID spelling and every shell fragment from that
> finding. And the digit pre-filter is sound only while no `_UNSET` member
> starts with a digit, which is now asserted instead of hoped for.
>
> Verified unchanged: 42 real jobs' `state`/`partition`/`account`/`work_dir`/
> `req_tres` against raw `sacct` (0 mismatches), the per-parse string sharing
> from round thirty-six, and SP-1 end to end -- 1,273 reported + 6 unterminated
> = 1,279 = `sacct -X | wc -l`, with `excluded_unparsed` at 0.

> **Round thirty-six, 2026-08-26.** Three defects, all filed against the published
> 0.8.2 by a cross-cluster evaluation on midway2 (CentOS 7.9, Python 3.14.6, Slurm
> 23.02, cgroup v1) and all three fixed here. 1842 tests at 0.8.2, **1882** here;
> all four gates clean.
>
> **Corrected after review, same day.** The first attempt at this round was reviewed
> against 15,086 real finished jobs (0 differences, so no regression on the common
> case) and four defects were found in the fixes themselves. All four are now closed,
> and they are worth recording because three of them are the same mistake: a rule
> applied to one field and not to its siblings.
>
> * **The memory block contradicted itself on a running job.** SP-28 routed
>   `Job.max_rss` through the new `Job.measured_steps` and left `ave_rss` on
>   `work_steps` and `max_vmsize`/`max_pages`/`rss_step_spread` on `steps`. So the
>   peak came from the live steps and everything printed beside it came from the
>   finished stragglers SP-28 exists to reject. Job 53834744 on midway3, running:
>   `● MEM 0.0% · 12.7 MiB of the 50.0 GiB limit so far` on one line and
>   `average 2.2 GiB` on the next -- an average **181x the peak** -- with `--json`
>   carrying `peak_bytes 13271040` beside `average_bytes 2409766912`,
>   `virtual_to_resident 5852.9` and `step_spread 1142.4`. All five now read
>   `measured_steps`, keeping each one's existing treatment of `.extern`. The same
>   job now reports peak 12.7 MiB, average 8.2 MiB, imbalance 1.55x, spread 3.08,
>   `virtual_to_resident 36.2`. Re-measured over 19,888 finished jobs from this
>   cluster: **0 differences** in any of the four, which is what
>   `measured_steps == steps` for an ended job guarantees.
> * **A stale open record is no longer "in progress".** `Job.in_progress` keyed
>   purely on state, so a record with `State=RUNNING`, `End=Unknown` and `squeue`
>   answering that it has never heard of the id -- the case `_mark_open_records`
>   exists to detect, four of them in this history -- was treated as unflushed. That
>   made `measured_steps` drop every step it has, so a dead record whose steps DID
>   flush a real MaxRSS would report `None` and lose a final measurement. `live is
>   False` is a measurement and the state is not, so it now wins; `live is None`
>   (not asked, or `squeue` unreachable) deliberately does not, because "no answer"
>   is not evidence a job is gone. Those four records read `total_cpu 0.0` again
>   rather than `None`. Their `Elapsed` is still measured to *now* and they are still
>   excluded from the aggregates, which is what the open-record finding says.
> * **`_parse_live_metrics`' "nothing measured" guard passed rows that had measured
>   nothing.** `all(v in (None, "") for v in measured.values())` reads as its own
>   name, but `NTasks=0` is neither `None` nor `""`, so job 53834744's
>   `53834744.extern|||||||213503982334-14:25:51||0` was stored with every useful
>   field empty. The guard now tests only the five keys that are readings, not the
>   labels or the step's shape. Harmless before -- `_apply_live_metrics` only fills
>   fields that are `None` -- and recorded because the test that covered it was
>   asserting the stored row rather than the discarded counter.
> * **The `--sizing` green-branch control asserted nothing.** It checked that the
>   sentence appears in `inspect.getsource(render_sizing)`, which passes just as
>   well if the branch is unreachable dead code -- this suite's named recurring
>   failure mode. It now patches `recommend` to return a non-actionable `keep` over
>   a history with groups, reaches the branch, and asserts the sentence is emitted.
>
> **SP-28 is the one to read.** For a job that is still running, `sacct` has flushed
> nothing, so the peak was taken over whatever short-lived steps had already
> *finished* -- and a job holding 462 MiB against `--mem=512M` reported **2.2 MiB,
> 0.4%**, with `peak_trustworthy: true` beside it. A 210x understatement on the
> gauge whose whole purpose is to say whether memory was the problem. What makes it
> likely rather than exotic is that *watching* the job creates the phantom step: an
> `srun --overlap` monitor -- slurmwatch's own node hop, or an interactive probe --
> leaves a ~2 MiB finished step behind, so using the sibling tool on a job made this
> one's post-mortem of it worse. A job nobody watched reported `n/a`, which was
> honest only by luck of the draw.
>
> It reproduced on a second cluster during the fix, in the *other* direction: job
> 53834744 on midway3 had live steps holding 12.7 MiB and a finished `.0` step at
> 358 MiB, so the same code would have overstated by 28x. The direction is luck; the
> mechanism is not.
>
> `sstat` has the right figure at the same instant, is available to the job's owner
> from a login node, and is what slurmwatch already reads. `sacct.read_live_metrics`
> now asks it -- one call per history, and only when some job is non-terminal -- and
> writes the answers into the live steps. Beside that, two rules that hold whether or
> not `sstat` answers: a running job's counters are read from its **live** steps only
> (`Job.measured_steps`), and a live step's `TotalCPU=00:00:00` is treated as *no
> reading* rather than as zero CPU, which is what rendered a job spinning at 100% of
> a core as `0.0 of 1 cores busy`. The allocation row is no longer a CPU fallback
> while a job runs: the two clusters measured disagree about whether that field is
> even updated live -- one showed `16:58` for a job whose steps summed to five
> seconds, the other `00:00.452` for the job at 100% of a core.
>
> **What a consumer sees change.** `--json` gains three memory fields
> (`peak_source`, `job_in_progress`, and a `peak_trustworthy` that is now false for
> *any* unfinished job), so a payload is **101** job-level values where it was 99.
> `memory.peak_bytes`, `memory.utilization`, `cpu.total_seconds` and
> `cpu.utilization` now come back **null** for a running job whose live steps have
> not been measured, where they previously carried a figure taken from another step.
> In `--plain` the MEM caption gains ` so far` on a running job, and CPU reads `n/a`
> where it read `0.0%`. Nothing changes for a job that has ended.
>
> **SP-27** -- history is fully materialised and nothing bounded it. Measured over
> 13,321 real jobs and 30,339 steps: 19.4 MB of string payload, of which ~10 MB in
> the top fourteen fields alone was exact *duplication* -- `uid` and `account` each
> had **one** distinct value held as 13,321 separate string objects, `state` seven,
> `flags` three, `work_dir` 35, `req_tres` 205. The parser now shares one object per
> distinct value, scoped to the parse: **2,034 -> 1,020 bytes retained per row**, and
> peak RSS on that query 162.9 MB -> 124.1 MB. `sys.intern` was rejected deliberately
> -- its table is global and never freed, so a long-lived process would accumulate
> every job id and timestamp it ever saw.
>
> The overview also now discloses the footprint above 20,000 parsed rows (`43,660
> rows parsed, about 42.6 MiB held -- a window ten times longer costs ten times that;
> narrow it with -S`), because what actually stopped users hitting the old limit was
> `SLURMPAST_TIMEOUT` failing on time before it failed on memory: an undocumented
> memory cap. **Streaming reduction is not done.** The aggregate views are all
> reductions and could accumulate as rows arrive rather than holding the record set,
> which is SP-27's first suggestion and the one that would remove the growth rather
> than halve it; it is an architectural change across `index`, `patterns`, `nodes`,
> `sizing` and the TUI, and it is still **Open**.
>
> **SP-29** -- `--sizing` rendered a *zero-workload* result as the green "every
> workload is already about right", because the two counters the 0.8.2 fix tested
> were both 0. Reachable from an empty window and, more consequentially, from a named
> RUNNING job -- which is filtered out before the counting and so registered as
> neither category, so a job at 94.5% of its memory limit was told it was about
> right. Now grey, and it names the job: `job 48853296 is still running -- --sizing
> needs a finished run`.
>
> One sibling finding recorded in the same round is also fixed: on a compute node
> with no passwd entry, `sacct` fails with `Invalid user id: youzhi` and the attached
> advice said *"Check the -u argument"* about an argument nobody passed, for a name
> that was the login name. It now names the real cause -- the node cannot resolve it
> -- and what to do about it.

## Round eighty-four — the documented red is gone: the badge test was reading the wrong tree

**Two reds going in, ZERO going out.** For eight consecutive rounds this file has ended with
"one red going out and it is the documented badge test". It is no longer red, and not by being
silenced.

**SP-A (fixed) — the badge had been bumped to 2526 again, and it broke the same control again.**
A helper working this tree set the README badge from 1969 to 2526 and was interrupted before
committing anything, leaving the published README stating a count for a suite nobody can
install. `test_badge_mismatch_diagnosis.py::TestControls::test_the_badge_still_states_the_committed_count`
caught it — the test that exists precisely to catch it. Reverted to 1969, byte-identical to
HEAD (`git diff -- README.md` empty). **This is the second time the same bump has been made and
undone** — round eighty-three did it (1969 → 2319) and recorded the undo. The rule is unchanged
and now has two incidents behind it: the badge moves in the same change that commits the tests,
never before.

**SP-B (fixed) — `test_the_test_badge_matches_the_suite` compared the badge against a tree that
does not ship.** The badge documents the PUBLISHED package; the test collected the WORKING tree.
Those differ for the whole life of a round, so the test failed on every round that left the tree
dirty, and round seventy-six's response was to add a module explaining the failure rather than
to correct the measurement. Explaining a permanent red is not the same as not having one: a test
that always fails locally teaches everyone to skip past it, which is exactly how a genuinely
stale badge would get through.

It now collects **HEAD** — `git archive HEAD` into a temporary directory, collected there with
that tree's own `src` first on `PYTHONPATH` so it imports the code that ships with it — and
falls back to the working tree when git cannot answer (a tarball install, no git binary). That
fallback is why `_badge_mismatch_reason` keeps its untracked branch: it is now the only path
where untracked files can explain a mismatch.

**Measured, and the obvious fix was wrong.** HEAD collects **1969** and its badge reads **1969**,
so the committed state was self-consistent all along and CI was green for the right reason. The
same tree live-collects **2526**. Dropping only the 27 untracked test files gives **1985**, not
1969 — because uncommitted work also adds tests to files that ARE tracked (+16). So "ignore what
is untracked", the fix this looked like from the diagnosis message, would still have failed by
sixteen. Only collecting HEAD answers it.

**Teeth, one site at a time.** Badge back to 2526 → the control fails **and** the badge test
fails (2 failed, 10 passed). Branch-local override forcing the live collect, badge left correct
→ the badge test fails (1 failed, 11 passed). And the check that the fix did not simply make the
test toothless: fix in place, badge set to a genuinely stale 1900 → the badge test **still**
fails. Ten controls pass in every one of those states; all twelve pass with both fixes in.

**Gates:** `ruff check .`, `ruff format --check .`, `mypy src/ tests/` all clean; suite
**2526 passed** in two halves (1015 + 1511), no reds.

## Round eighty-three — landing rounds seventy-nine to eighty-two: three tests that could only pass on this cluster

2518 collected before, **2526** after (+8); `ruff`, `ruff format` and `mypy src/ tests/`
clean, coverage **97%** against a `--cov-fail-under=75` gate. The round has no red going
out: the badge test that rounds seventy-six to eighty-two each recorded as an expected
local failure closes here, because the tests it was counting are now committed.

Found by running the suite the way CI runs it rather than the way this host runs it —
**with Slurm stripped from PATH** (`sacct`, `sinfo`, `squeue`, `scontrol` and `sstat` all
live in one directory here, so removing it is exact). Three tests written in the previous
four rounds passed on a login node and could not have passed on a runner. That is the
defect class this file has now named for the fourth time, in the tests rather than in the
code, and the CI workflow already claims the property they broke: *"every test drives the
parser and the dashboard through fixtures or the built-in synthetic history, so nothing
here shells out to sacct."*

### SP-30 (fixed) — a signal during dashboard startup restored nothing, and exited 143 anyway

The genuine product defect of the round, found because the test written for round
eighty-one's terminal guard failed **1 run in 5** with
`{'opened': 1, 'closed': 0, 'signalled': False, 'code': 143}` — an exit code proving the
handler had run beside a capture proving the screen was never restored.

`_guard_startup_window`'s `_restore_and_die` (`tui.py:2615`) wrote `_TERMINAL_RESET`
through `sys.stdout`, choosing between `sys.stdout` and `sys.stderr` on `isatty()`. But
the window it exists to cover *opens* when Textual emits the alternate-screen sequence,
and Textual replaces both streams with capture objects at about that same moment. Their
`write` queues into the app instead of reaching the terminal and their `isatty()` still
answers True, so the guard wrote the restore into a capture and `os._exit(143)` a
microsecond later dropped the queue. Whether the signal beat the redirect decided it,
which is why the real dashboard showed it only sometimes — and the exit code made every
occurrence look handled.

Reproduced deterministically with a stand-in capture in both streams, which is what the
docstring predicted a capture would do:

```
                              TERM        HUP
sys.stdout version            143, no \x1b[?1049l   129, no \x1b[?1049l
descriptor version            143, restored          129, restored
```

The restore now goes to the terminal's **file descriptor** (`os.write` on 1, else 2,
chosen by `os.isatty`), which nothing can redirect. Codes are unchanged (143/129) and the
post-mount handlers are untouched.
`tests/test_portability_round81.py::TestASignalInTheStartupWindowStillRestores`. Teeth:
restoring the `sys.stdout` version reddens the deterministic test 2 of 2 and the live pty
test intermittently. **The control** — the same child with its streams left alone — passes
in both states, which is precisely why the defect could hide: unredirected, `sys.stdout`
*is* the terminal.

### SP-31 (fixed) — three tests asserted the answer this cluster gives

Each reproduced with Slurm off PATH, then made to hold in both environments rather than
skipped:

* `TestAnEmptyIdentityIsRefused::test_a_real_value_and_an_absent_flag_are_untouched`
  queried the live scheduler with `-u youzhi -p amd` — this cluster's login name and one
  of its partitions — and asserted `rc in (0, 1)`. With no `sacct` that is rc=2 and
  "cannot execute sacct", so the control passed where it was written and reddened
  everywhere else. It now runs `--demo` on the tape's **own** user and partition, read out
  of `demo.history()` rather than hardcoded. The empty-value check runs before the
  `args.demo` branch in `_main`, so `--demo` reaches the same code with no scheduler in
  the picture — pinned by a new test, without which the control could stop asserting
  anything and still pass.
* `TestASignalledDashboardRestoresTheTerminal` drove `python -m slurmpast` with no
  `--demo`, so on a runner the child entered the alternate screen, failed its load and
  returned the load error's 2 before any signal arrived: `SIGHUP` reported
  `{'code': 2, 'entered': 1, 'left': 1}` against an expected 129, and the other three
  cases found no live process to wait for. Both pty harnesses now drive `--demo`, which
  needs no scheduler and renders identically on a login node and a runner.
* `test_sizing_routing.py`'s `plain` fixture was **module-scoped**, so pytest built it
  before `conftest`'s function-scoped autouse `_pinned_site` — the surface was rendered
  against the host's `scontrol show config` while every `Advice.caution` compared against
  it was computed under the pin. On this cluster the two strings happen to be equal, so
  the ordering was invisible; with no `scontrol` the surface said "depending on this
  cluster" and the caution said `jobacct_gather/linux`, and `test_the_caution_is_on_both`
  failed for a reason that had nothing to do with routing. Function-scoped now, so the pin
  is in place before the render.

### SP-32 (fixed) — a harness that declared a hang without waiting, and one whose capture could lose the bytes it asserts on

`TestASignalledDashboardRestoresTheTerminal._drive` polled with
`for _ in range(40): pump(0.4)`, which reads as a 16-second budget and was not one: `pump`
returns the moment the pty master reports EIO, and the master reports EIO at **0.22 s**
after the signal while the child is reaped at **0.42 s**. So the loop spun forty times in
microseconds and called it a hang — 2 failures in 3 runs, always "the dashboard did not
exit", never the same signal twice. Bounded by the clock now, with a sleep pacing the poll
once the stream is at EOF, and finite rather than a blocking `waitpid`, because a suite
with no global timeout turns one of those into a wedged CI job instead of a failing test.

The startup-window harness had the sibling problem in its capture: EOF on a pty master
means the last slave fd is gone, and the kernel may drop whatever is queued at that
moment, while both children here write their final bytes and `os._exit` microseconds
later. The parent now holds a second fd on the slave for the whole run and closes it only
after the child is reaped, which is what ends the drain. Recorded honestly: **nothing
measured here was ever traced to that discard** — the loss that looked like it was SP-30 —
but a harness whose result turns on which of two microseconds wins is not one to assert
on. The plumbing is shared by both tests in the class now (`_drive_in_a_pty`) instead of
duplicated, and it uses `pty.openpty` + `fork` rather than `pty.fork`, which closes the
slave in the parent; `os.ptsname`, which would let the parent re-open it, is 3.13+ and
this package's floor is 3.10.

### The badge

`tests-1969` in the README, **2526** collected. Round seventy-six added the diagnosis that
tells the two causes apart, and it read this tree correctly for seven rounds: the badge
states the count of the suite that SHIPS, twenty-eight test files were uncommitted, and
bumping it early would have redded CI. Landing them is what closes it, so the bump belongs
in the same commit as the files — set to a measured `--collect-only`, re-measured after
every test edit in this round (2518 → 2519 → 2523 → 2526 as the fixes above added tests).

One test of that diagnosis had the same shape as SP-31 in miniature:
`test_it_reports_this_repo_s_untracked_tests` asserted the probe could see **its own
file**, which is true only while that file is uncommitted and false the moment the round
lands — a test that reds CI on the commit that adds it. It now asserts the property that
holds in both states (everything reported is genuinely untracked, checked against
`git ls-files`), and the positive case is arranged in a scratch repository the test builds
itself rather than borrowed from this checkout.

## Round eighty-two — the bar claimed full where its own label said 98%

2416 collected before, **2518** after (+102); `ruff`, `ruff format` and `mypy src/ tests/` clean.
One red going out and it is the documented badge test (round seventy-six).

### SP-7 (fixed) — `bar_cells` never reserved its last cell, so two of three paths drew solid early

`bar`'s docstring states the rule for the whole function: *"Two rules keep the bar honest against
the number printed beside it: the last eighth is withheld until the percentage rounds to 100, so a
visually full bar always means 100%; and anything that displays as >=1% keeps at least a sliver."*
Its Unicode branch obeys both. The other two branches — `ascii_mode`, and `flat`, which is what
the **plain report** draws with — delegate to `bar_cells`, which had only the sliver rule.

Measured at widths 8 and 18, before:

```
        unicode      ascii        label
98.0%   ███████░     ########     "98.0%"   <- ascii solid, unicode not
99.6%   ███████░     ########     "99.6%"
99.9%   ███████░     ████████     "99.9%"
```

Every value from roughly 97% up disagreed between the two paths, under one shared label. And
`bar_cells`' own docstring already records fixing this exact class of disagreement at the LOW end:
"Using a bare `>= 0.5` here instead made the ASCII and Unicode bars disagree over 0.5-0.94%: one
lit a cell beside a label reading '0.7%', the other did not." The rule was stated; the top end had
drifted from it.

The reservation is keyed on `round(percent, 1) < 100.0`, exactly as `bar()` keys its own, because
the labels here carry one decimal: at 99.96% the label reads "100.0%" and the bar is meant to be
solid. Verified after: all three paths agree at every value tested, and the solid bar begins
exactly where the label reads 100.0%.

**Sibling of the slurmwatch fix in the same family.** There the LABEL rounded up to 100 and both
bar guards keyed on the rounded value, so bar and label claimed 100% *together*; here the label
was honest to one decimal and two of the bars were not. Same invariant, opposite halves.

`tests/test_bar_fullness_agrees.py` (102 tests). Teeth: removing the reservation reddens **57**.
**Twenty controls, all re-run green in the neutered state**, pinning every ordinary cell count as
MEASURED (25% of 18 is 4.5, which `round` takes to 4 — banker's rounding, and an expectation
written from the arithmetic said 5), the sliver rule, `None` and NaN drawing an empty track, zero
width, an over-range clamp, and the Unicode path being untouched.

## Round eighty-one — the repeat-failure advice said two things that were not true

2400 collected before, **2416** after (+16); `ruff`, `ruff format` and `mypy src/ tests/` clean.
One red going out and it is the documented badge test (round seventy-six).

Both items were already written down in round five's **"Open — reported, not changed"**, and both
were re-measured on a live 30-day history before anything was touched.

### B (fixed) — "Stop resubmitting" to a workload submitted once, "deterministic" to one that succeeded

Re-measured, and it is worse than the entry recorded — the determinism half is false on a second
workload the entry never named:

```
cpas_audit  n=11  distinct_masters=1  {FAILED: 8, COMPLETED: 3}
  Stop resubmitting; the failure is deterministic. Reproduce interactively.
cpas_G1     n=100 distinct_masters=1  50 failed / 50 completed
  Stop resubmitting; the failure is deterministic. Reproduce interactively.
```

`cpas_audit` is ONE `sbatch --array`: there is nothing to stop resubmitting. Three of its eleven
tasks COMPLETED, so the failure is not deterministic either. `cpas_G1` completed **half** its runs
and was told the same thing.

After:

```
evidence: 8 of 11 runs of cpas_audit in test failed; 8 were FAILED. All 11 are tasks of one
          array (job 53410199).
action  : One array submission, not repeated ones: reproduce a single task interactively rather
          than resubmitting the array. 3 of 11 tasks completed, so the failure is not
          deterministic — compare a failed one against a completed one.
```

**The entry's own constraint is respected**: this is NOT fixed by exempting arrays from the
grouping. The counts are untouched — "8 of 11 runs failed" stays, because those eleven
allocations ran and burned resource, which `TestArraySiblingsAlreadyCountAsEvidence` pins
deliberately. Only the advice moved. The two facts it needed were already in the record: the
master id (everything before the `_`, exactly as the entry suggested) and `Job.completed`.
Severity is still `fraction > 0.8` and no exit code moves — which is what separates this from
item **A** in the same entry, still open because it *does* move a published severity and
`cli.py`'s exit 1, and its own note says the decision is the maintainer's. Untouched.

### C (fixed) — `newest_name`'s docstring described a tie-break `build_groups` does not have

It claimed members are ordered "the way `index.build_groups` orders a group's members ... with
`numeric_job_id` breaking the tie". `build_groups` is `members.sort(key=lambda j: _stamp(j),
reverse=True)` — no second key. The tie-break is real but it is `newest_name`'s own, and ties are
the ORDINARY case here because an array's tasks share a Submit. The docstring was the wrong half,
as the entry said; it now describes what the function does and names the difference.

`tests/test_repeat_failure_action_is_true.py` (16 tests). Teeth: neutering the array branch
reddens 1, the determinism clause 3, the evidence sentence 1. **Eight controls, all re-run green
in every neutered state**, pinning that the classic sentence is byte-identical, that no group
starts or stops firing, that severity does not move (WARNING at 6/8, CRITICAL at 8/8), that the
TIMEOUT and OUT_OF_MEMORY actions keep their own text, and that array siblings still count as
evidence.

## Round eighty — the interval round's own two tests could not have caught it

2389 collected before, **2400** after (+11); `ruff check .`, `ruff format --check .` and
`mypy src/ tests/` clean. One red going out and it is the documented badge test (see round
seventy-six for why it stays).

No production code changed. This round is an audit of round seventy-nine's own evidence, and
it found two tests that pass with the fix reverted and one docstring claim wider than the fix.

### SP-6a (fixed) — `test_the_dashboard_cell_agrees_with_the_helper` was a tautology

It asserted `ci_range(0.9996, 1.0) == format_rate_range(0.9996, 1.0)`, and `render.ci_range`
(`render.py:1005`) is literally `return format_rate_range(low, high)`. So it held with the
local `%.1f` restored, and there is no input for which it could fail — it was the round's only
claim that the *dashboard* carried the new spelling, and it made no claim about the dashboard
at all.

Agreement between the two surfaces cannot be the assertion, for the same reason: both call the
one helper in either state. What can fail is the **bounded spelling reaching both screens**, so
the interval is now driven into the band by the data and both real renderers are asked what
they printed:

```text
nodeA: 8000 FAILED, nodeB: 200 COMPLETED   ->  wilson_interval(8000, 8000) = [99.952%, 100%]

report.render_nodes(...)                        _nodes_screen_text(...)  (Textual harness)
  nodeA   8000/8000  100.0%  >99.9 – 100.0%      nodeA  8000/8000  100.0%  >99.9 – 100.0%
```

7680 is the smallest table for which this package's own statistics reach the band at all, which
is why the fixture is that size; it costs ~0.13 s to build and the whole file runs in 3.2 s.
With the local `%.1f` restored **both** renderers print `100.0 – 100.0%` — measured, not
assumed, and that is the test's teeth.

### SP-6b (fixed) — `test_the_format_is_not_re_derived` asserted on source text

It read `duration.py`, sliced out `format_rate_range`'s body and asserted `"%.1f" not in` it.
That pins the implementation rather than the behaviour: it detects a *reverted edit* and would
go red on a rewrite that spelled every band correctly by other means. Replaced by the property
the fix actually claims, asserted on output — each end of a range is byte-identical to
`format_percent` of that end — parametrised over eight values spanning every band
`format_percent` distinguishes (`0.0`, `0.0004`, `0.0006`, `0.246`, `0.5`, `0.9994`, `0.9996`,
`1.0`). No independently derived `%.1f` can satisfy it, because it disagrees at both bounded
bands; two of the eight redden under the neuter.

### SP-6c (narrowed) — the module docstring claimed more than the fix does

It opened "a range whose two ends print identically says the measurement was exact, and this
one is not". That is not true as a general rule and this change does not make it true. Measured
**with the fix in place**:

```pycon
>>> format_rate_range(0.50001, 0.50009)
'50.0 – 50.0%'
>>> format_rate_range(0.0006, 0.0009)
'0.1 – 0.1%'
```

Left alone deliberately, and a different thing: an interior tie is the printed *resolution*, the
same one decimal place every `50.0%` in this tool carries, so a reader who takes it as exact is
over-reading a rounded figure rather than being told something false. The two boundaries are
claims of a different kind — `100.0%` of a failure rate means *nothing succeeded* and `0.0%`
means *nothing failed*, each being where the reader stops looking — which is exactly the band
`format_percent` governs. Closing the interior ties would mean `%.2f` on every interval the tool
prints, the option round fifty-six weighed and declined, and would only move the tie to the
third decimal. **The fix is not widened**; the docstring now says which two values are claims,
and `TestControls::test_an_interior_tie_is_left_alone` (3) pins the three measurements above so
the narrowed claim is asserted rather than only written.

`tests/test_interval_boundary.py` is now **31 tests** (was 20). Teeth: restoring the local
`%.1f` reddens **10** (was 8), the two new ones among them. **15 controls**, every one
re-verified green in the neutered state — the eleven round seventy-nine had, plus the three
interior ties and a fixture control asserting `wilson_interval(8000, 8000)` really reaches the
band, without which the cross-surface test could pass on an ordinary interval.

## Round seventy-nine — closing the interval defect round fifty-six left open

2369 collected before, **2389** after (+20); `ruff`, `ruff format` and `mypy src/ tests/` clean.
One red going out and it is the documented badge test (see round seventy-six for why it stays).

### SP-6 (fixed) — `format_rate_range(0.9996, 1.0)` read `100.0 – 100.0%`

Round fifty-six filed this under **Open — the same defect one helper over, NOT fixed here**, and
its recorded reason has two halves. Both are answered here rather than stepped around.

> "a range shows both ends, so it needs its own decision about whether `>99.9 – 100.0%` reads
> better than widening the precision"

The decision was already taken, one helper over: `format_percent` renders a single value in
[99.95%, 100%) as `>99.9%`, and its docstring argues the case three ways (2000 jobs with one
failure reading "100.0% completed"; one failure in 13,051 reading "0.0%"; `walltime_used` at
99.96% reading "100.0%" for a job that did not hit the wall). Routing each end of the range
through it adds no fourth spelling and invents no precision, where widening to `%.2f` would
change every interval the tool prints in order to answer one boundary.

> "and `ci_range`'s spelling is pinned in three places"

Measured, and they do not move: `test_audit.py:1215` (`ci_range(0.757, 1.0) == "75.7 – 100.0%"`),
`test_comparison_population_disclosure.py:108` (`95% CI 72.2 – 100.0%`) and
`test_interval_spelling.py` (which pins that `ci_range` must not re-derive the format). The first
two have ends that `format_percent` renders identically — the exact boundaries stay exact — and
the third is about ownership, which is unchanged: `duration` still owns the one format. All three
files were re-run with the fix in place: **97 passed**.

The surviving case worth naming: when both ends fall in the same bounded band the range reads
`>99.9 – >99.9%`. That is not the old defect renamed — it says neither end reached 100%, which is
true, where `100.0 – 100.0%` said both were exactly 100%, which was false. Pinned.

`tests/test_interval_boundary.py` (20 tests). Teeth: restoring the local `%.1f` reddens 8.
Eleven controls, all verified green in the pre-fix state, covering every previously pinned
string, the `--ascii` fold, the single `%` at the end, `ci_range`'s delegation, and
`format_percent` itself being untouched.

**Superseded by round eighty**: two of those twenty tests turned out to pass with the fix
reverted, and this round's docstring claimed more than the fix does. The counts above are
the ones as filed; the file is now 31 tests, 10 of which redden under the neuter, with 15
controls.

## Round seventy-eight — two `--plain` notes printed at whatever length they happened to be

2348 collected before, **2369** after (+21); `ruff`, `ruff format` and `mypy src/ tests/` clean.
Two reds going out, both known: the documented badge test (see round seventy-six) and
`test_portability_round81.py::TestASignalledDashboardRestoresTheTerminal::test_a_clean_quit_is_still_zero`,
which is the SP-2 quit-linger timing flake — it passes on its own and passed on a full re-run of
its own file (90 passed).

### SP-5 (fixed) — the footprint note and the truncation summary were the only paragraphs not wrapped

Found by running the tool at several widths and measuring every painted line, rather than by
reading the code:

```
$ COLUMNS=90 slurmpast --no-color -S now-14days --overview | awk 'length($0)>90'
  40,994 rows parsed, about 40.0 MiB held — a window ten times longer costs ten times that; narrow it with -S
$ COLUMNS=60 ... | awk 'length($0)>60'
  … 354 more workloads (8262 runs) holding 14.0% of the compute
```

The footprint note is 109 cells and overran at **every** width tested (60, 70, 80, 90, 100),
including the 90 and 100 a real terminal is. The truncation summary is 63 and overruns
`PLAIN_MIN_WIDTH`, the floor `_plain_width` clamps to.

`report.py` states the rule this breaks, in `_prose_width`'s own docstring: the paragraph widths
"were hardcoded at 72, 82 and 84, so a finding hard-broke mid-sentence two thirds of the way
across a wide terminal and overran a narrow one." Nine paragraphs go through
`wrap(..., _prose_width(n))`. These two did not.

Fixed at both print sites in `report.py` (`render_overview`). The truncation summary keeps a
hanging indent — `  … ` then four spaces — because it sits directly under a table, and a
continuation flush with the rows above reads as another row. Neither note is drawn by the
dashboard (checked: `tui.py` and `render.py` mention neither), so there is no second surface to
keep in step.

`tests/test_plain_notes_are_wrapped.py` (21 tests). Teeth verified by neutering each wrap site
separately: the footprint site reddens 8, the tail site 1. Controls that pass in both states: a
150-column terminal keeps each note on one line, a small history still prints no footprint note,
the threshold boundary still holds, `-n 0` still prints no truncation summary, and the demo's own
54-cell tail still fits the 60-cell floor on one line.

One existing test was updated rather than left red:
`test_portability_round81.py::test_the_footprint_is_disclosed_on_a_large_window` asserted
`"narrow it with -S" in text`, which a wrapped note can legitimately straddle. It now flattens the
text first — the property is that the advice is disclosed, not where the break falls.

## Round seventy-seven — the two surfaces disagreed about how to say "no node"

2333 collected before, **2348** after (+15); `ruff`, `ruff format` and `mypy src/ tests/` clean.
One red going out and it is the documented badge test (see round seventy-six for why it stays).

### SP-4 (fixed) — `NODE` was the one cell of twelve where `--plain` and the dashboard differed

`CLAUDE.md` states the rule: "`render.py` exists so the dashboard and `--plain` cannot drift."
The job table is drawn by both from the same twelve `JOB_COLUMNS`. Eleven agreed:

| column | `--plain` | dashboard |
| --- | --- | --- |
| STARTED | `or "-"` | `or "-"` |
| ENDED | `or "-"` | `or "-"` |
| GPU | `or "-"` | `or "-"` |
| NAME | `or ""` | `or ""` |
| **NODE** | **`or "-"`** | **`or ""`** |

So the convention was settled everywhere else in that same dict, and the dashboard was the
outlier. It matters because a job with no node list is a real state -- pending, or cancelled
before it was ever allocated -- not an inapplicable column: an empty cell reads as "this column
does not apply to this row", while `-` is this tool's marker for a value it does not have. The
same distinction the package draws everywhere between an absence and a zero.

The width computations still use `or ""` on both sides and that is right: they size the column
and an absent value contributes no characters, while the four-wide `NODE` heading floors it, so a
one-character `-` cannot be truncated. Measured after: a nodeless job renders `... n/a - -` and
one with a node renders `... - midway3-0042`.

`tests/test_node_absent_marker_agrees.py` (15). The marker is read off BOTH sources rather than
restated, so the test cannot drift from the code the way the code drifted from itself. Teeth:
reverting the dashboard cell to `or ""` reddens 3; all 12 controls pass in both states -- and the
`--plain` side is deliberately among them, being the side that was already right.

## Round seventy-six — a failed `sinfo` memoised, an unbounded `sstat`, and the quit that never exits

2307 collected before, **2333** after (+26); `ruff`, `ruff format` and `mypy src/ tests/` clean.
Five reds going in; **one red going out, and it is the documented badge test** — the four signal
failures were a CONSEQUENCE of SP-3 and went green with it.

**A correction this round made and then undid.** The badge was bumped 1969 -> 2319 to "fix" the
documented red, which **broke `test_badge_mismatch_diagnosis.py::TestControls::
test_the_badge_still_states_the_committed_count`** — a test that exists precisely to stop this.
Its module docstring says it in as many words: the tree holds untracked test files, so the badge
is *correct for the suite that ships*, the local failure is expected, and "Bumping the badge would
**red CI** — the opposite of the fix." Reverted to 1969, byte-identical to HEAD. The badge moves
in the same change that commits the tests, and not before.

### SP-1 (fixed) — `partition_ceiling` cached a query that failed

`partition_ceiling` is what keeps `--sizing` from advising a number the hardware cannot take;
its own docstring records the case, "`--cpus-per-task=34` on a partition whose nodes have 28,
which `sbatch` refuses outright". It is also explicit that a failure answers `(None, None)` and
never raises, and that is right. What went unsaid is that the failure was then written into
`_PARTITION_CEILING`, which is consulted **before** the query. Measured:

| call | `sinfo` | answer | cached? |
| --- | --- | --- | --- |
| 1 | raises `SacctError` | `(None, None)` | **yes** |
| 2 | works, returns `128 256000` | **`(None, None)`** | — `sinfo` never re-ran |

One transient failure — no `sinfo` on PATH yet, a timeout, an EINTR — therefore disabled the
clamp for the whole process, reintroducing the exact defect the function exists to prevent.

The fix withholds only the memo, on a single `answered` flag. The return contract is untouched
(still `(None, None)`, still never raises), and output that **answered** but would not parse
still caches, because that is a measurement about the partition: the distinction is the query,
not the verdict, which is the line this package already draws between a zero and an absence.
`tests/test_partition_ceiling_cache.py` (12). Teeth: `if answered:` -> `if True:` reddens 5, and
so does dropping `answered = False`; all 7 controls pass in both states.

### SP-3 (fixed) — the live `sstat` enrichment had no budget of its own

`merge_live_metrics` is built around a number it names outright: "the 18-second call this exists
to avoid". Measured on midway3 with **60 running array tasks**, the one batched call this module
makes — `sstat --allsteps --jobs=<60 ids>` — took **119.76s** for 2,160 rows. It contacts each
job's `slurmstepd`, so its cost scales with how many jobs the reader has RUNNING, not with the
window. Nothing bounded it but `DEFAULT_TIMEOUT = 300.0`, which is the *accounting database's*
budget. `slurmpast --plain` therefore sat for two minutes before printing anything, and this is
also what the `_load` worker in SP-2 is usually inside when the user quits.

`read_live_metrics` already documents the right answer for a failure: "the caller's fallback is to
report the field as unmeasured, which is the correct answer and not a degradation". So the query
gets its own `LIVE_METRICS_TIMEOUT_S = 15.0` and lands on that fallback. Waiting two minutes to
avoid printing "unmeasured" is the wrong trade.

Three deliberate details. **No new environment variable** — `SLURMPAST_TIMEOUT` is documented as
"the package's only environment variable", so it is honoured as a *ceiling* instead:
`min(_timeout(), timeout)` inside `_run`, so lowering it lowers this too while raising it does not
extend an enrichment. **`_timeout()` is still read first**, so a bad setting is refused before any
spawn, as its own comment requires. **The budget goes to `_run` directly, not through `runner`**:
all 48 injected runners in this package are one-argument callables and a test double has no wait
to bound, so the protocol is untouched.

Measured after: `_run(["sleep", "30"], timeout=2.0)` raises at 2.00s. The end-to-end `--plain` run
is **still ~171s**, because the bulk is elsewhere and the tool already says so in its own output —
"37,784 rows parsed, about 36.9 MiB held — a window ten times longer costs ten times that; narrow
it with -S". This fix bounds the enrichment, not the window.

### SP-2 (root cause still open; the fatal symptom is gone via SP-3) — quitting lingers

`tests/test_portability_round81.py::TestASignalledDashboardRestoresTheTerminal` is **4 red, and
not a flake**: it fails the same way run alone (170s) as in a full run. Every case dies on the
helper's own last resort, `pytest.fail("the dashboard did not exit")`.

Driven in a pty and timed, `sacct` being 0.12s and the alternate screen appearing at 0.46s:

    'q' sent -> alternate screen RESTORED at 0.21s   (clean: enter 1, leave 1, no traceback)
             -> process REAPED at ... 14.7s once, and never at all in 3 of 4 later trials

`--no-logs` changes nothing, so it is not the log-resolving worker. `faulthandler` on the hung
process names it exactly:

    main thread   asyncio/runners.py close -> loop.shutdown_default_executor()
    shutdown thr  concurrent/futures/thread.py:235 shutdown -> Thread.join
    worker thr    textual/worker.py run_callable -> tui._load -> cli.load
                  -> sacct.history -> sacct._query -> sacct.parse
                  -> duration.parse_bytes -> duration.py:60 <listcomp>

Textual's `run_worker(..., thread=True)` submits to asyncio's **default** executor, and
`asyncio.Runner.close()` joins it. The load worker is mid-parse, a parse cannot be interrupted,
so the interpreter waits — leaving an orphan burning CPU on a login node after the user has
already got their prompt back.

**Deliberately not fixed here, and SP-3 changed the picture.** Every remedy for the root cause
touches process-exit or threading semantics rather than a line of logic: Python 3.11's
`shutdown_default_executor()` takes no timeout (3.12 added one), the executor's own `atexit` hook
joins its threads regardless, and Textual creates the loop inside `App.run()`, so
`set_default_executor` is out of reach. The candidates are a daemon thread of our own for the
load, a cooperative abandon-flag checked inside `sacct.parse`'s row loop, or `os._exit` after the
terminal is restored — a design call, not polish.

**What SP-3 did to it, measured.** Capping the live query removed the unbounded part of the wait:

    before SP-3   screen restored at 0.21s | reaped at 14.7s once, NEVER in 3 of 4 trials
    after  SP-3   screen restored at 0.21s | exited in 21.3s, 21.4s, 21.3s (bounded)

So the orphan is gone and the four signal tests pass, because their budget is ~22s. **The linger
is still ~21s**, which is a long time to hold a terminal after the user has their prompt back, and
the join is still uninterruptible — the root cause is open, it is just no longer unbounded.

## Round seventy-five — three defaults stated in prose, and a sibling's note saying they were not

2298 collected before, **2307** after (+9); `ruff`, `ruff format` and `mypy src/ tests/` clean,
and the only red is the documented badge test.

`--since`, `--metric` and `--sort` each spell their default into the help text —
`(default: now-7days)`, `(default: hang)`, `(default: cost)` — rather than interpolating
`%(default)s`. Hardcoding is defensible (`--since`'s gloss, "'-7days' is accepted and rewritten
for you", reads better beside a literal) but it is a **copy**, and a copy drifts silently:
change the keyword and the sentence beside it still names the old value. Nothing checked them.

**Found by doubting a sibling's note rather than the code.** nodetop has this exact check, and
its docstring said: *"A sibling package sidesteps this by interpolating everywhere, and two
others state only prose defaults, so this is the one package where the check has anything to
bite on."* Half right. Measured across the family:

| package | stated defaults | drift possible? |
| --- | --- | --- |
| rapidu | 7, all `%(default)s` | no — interpolated |
| nodetop | 13 values + 3 prose | yes, and checked since `c03ef88` |
| **slurmpast** | **3 values + 1 prose (`--user`, "you")** | **yes, and unchecked** |
| slurmate | — | no `cli` module to import a parser from |
| slurmwatch | — | its `cli` exposes no `build_parser` |

So the sentence under-counted, and the two it lumped together are not comparable for a different
reason: their parsers are not reachable, which makes the help text the only surface and a
different probe. Corrected in nodetop as part of this round.

`tests/test_stated_defaults.py` is ported from nodetop deliberately unchanged in shape — the
same `(default: X)` regex bounded to 24 characters, the same semicolon-gloss handling, the same
by-name prose skip list, and the same emptiness guard that fails and says to delete the file if
the package ever moves to `%(default)s` throughout. A fix in one transfers.

Teeth, three drifts, each reddening exactly the flag that moved with all 5 controls and the
guard green:

| neuter | red |
| --- | --- |
| `--since` default → `now-14days`, help unchanged | `[--since]` |
| `--since` help → `(default: now-30days)`, default unchanged | `[--since]` |
| `--metric` default → `failure`, help unchanged | `[--metric]` |

The second row is the direction a copy usually drifts — someone edits the sentence — and it is
caught the same way, because the check compares the pair rather than trusting either side.

### Still open

* The badge/untracked-files item, unchanged.

## Round seventy-four — `--mouse` evaporated in every text mode

2283 collected before, **2298** after (+15); `ruff`, `ruff format` and `mypy src/ tests/`
clean, and the only red is the documented badge test.

The neighbour of round 73, found by looking one flag over. `args.mouse` is read at exactly one
place — `tui.run(mouse=args.mouse)` — so under `--plain`, `--json`, any section view or a named
job it is a flag that was typed and will not be used. This block already holds three remedies
for that class and `--mouse` had none of them:

* `--log-dir` (round 81) and `-S`/`-E`/`--all-users` under `--demo` (round 73) → a **warning**;
* `--steps` without a job id → a **`parser.error`**, and its comment states the class outright:
  *"It used to evaporate, so a caller who forgot the id got the ordinary overview and no hint
  that the flag they typed did nothing."*
* the `_has_terminal()` degrade → deliberately **silent**, for a reason it also states.

A warning, matching `--log-dir`: the report asked for still arrives exactly as asked, and only
the mouse preference is moot.

**The placement is the load-bearing part, and I got it wrong first.** `if not _has_terminal():
args.plain = True` degrades to text on a pipe and must stay silent — "a note on stdout would
corrupt the very file being written, and one on stderr would be noise in every CI log for a
fallback that did what was wanted". My first version sat AFTER that assignment, so
`--demo --mouse | cat` warned about a mouse the caller had never asked to drop. Measured, moved
above the degrade, and re-measured: `--demo --mouse` piped is silent again while every explicit
text mode warns. A control now pins that case, and it is the regression guard for the placement
as much as for the behaviour.

The components mirror `wants_text` and take the section names from `SECTION_ORDER`, so a sixth
section reaches both or neither.

Teeth: removing the block reddens **8**, all 5 controls green — including the pipe case and
`--steps`' stricter remedy, which this round leaves alone.
`tests/test_mouse_needs_the_dashboard.py`, 15 tests.

**Also measured and NOT changed, on the same sweep:** `--plain --json` silently prefers JSON,
and `--overview --patterns --nodes --sizing` compose additively. Neither is a dropped flag —
`--plain` is a degrade switch that `--json` refines rather than contradicts (its own help says
it is "automatic when stdout is not a terminal"), and the composed sections are what `--help`
shows as an example. `--json` with two sections is already a `parser.error` naming the fix.

### Still open

* The badge/untracked-files item, unchanged.

## Round seventy-three — `--demo` dropped a window and an audience without saying so

2271 collected before, **2283** after (+12); `ruff`, `ruff format` and `mypy src/ tests/`
clean, and the only red is the documented badge test.

Round 81's `TestADroppedFlagIsReported` set the rule and the wording — a flag asked for and not
used earns a warning on stderr, not silence and not an error — and it explicitly named `--demo`
as a route that makes flags no-ops: *"it sets `no_logs` itself ... so `--demo --log-dir X` was
equally silent."* It fixed `--log-dir`. Two more flags arrive by the same route and were still
silent:

* **`-S/--since` and `-E/--until`.** Both render sites read
  `"synthetic demo data" if args.demo else humanize_window(...)`, and the query gets
  `since=None if (args.demo or args.until)`. Measured: `--demo -S now-1days` and
  `--demo -S now-365days` render **byte-identical** output to `--demo` alone (md5 `d4de7f5765`
  all three).
* **`--all-users`.** `demo.history()` yields 58 jobs belonging to **one** user, so there is
  nobody to widen to. Also byte-identical, on `--json` as well.

Now one warning, comma-joined when several apply, beside `--log-dir`'s and worded the same way
with its own reason: `-S/--since, --all-users has no effect with --demo (a fixed tape of one
user's jobs); ignoring`.

**Compared against the parser's OWN default, not truthiness.** `--since` defaults to
`now-7days` and is therefore always set, so a truthiness test would warn on every `--demo` run
and say nothing about what the caller typed. The default is normalised for the comparison
because `args.since` already is, or the check would fire on spelling alone. **The cost, recorded
rather than hidden:** typing the default explicitly (`--demo -S now-7days`) is indistinguishable
from not typing it, because argparse keeps no record of which happened without a sentinel
default — and changing the default to one is a wider change than this warning is worth. A
control asserts that case stays silent.

On **stderr**, so `--json` still parses and `--plain` is byte-identical — both asserted, because
a diagnostic on stdout would corrupt the payload this package is scripted through.

Teeth: removing the block reddens **7**, all 5 controls green.
`tests/test_demo_reports_its_dropped_flags.py`, 12 tests.

**One control had to be rescoped after measuring it.** It originally asserted that a real
(non-`--demo`) run reports `Invalid time specification` for `-S not-a-date`. Under the narrow
`PATH` the test gives its subprocess there is no `sacct`, so the run stops earlier with "cannot
execute sacct" — the correct message, and exactly what a CI runner sees. It now asserts the
portable property instead: rc=2 and **no** `--demo` warning. A control that needed a live
scheduler would have passed here only because this host is a cluster, which is the inverse of a
runner and a defect class this family has shipped before.

**Found by a sweep that came back clean otherwise.** The axis was "does `--json` stay parseable
on the error branch, or does a diagnostic land on stdout" — checked across all five packages,
ten failure paths, and **every stdout was either empty or valid JSON**. The `--demo` finding
came out of a confounded reading in that sweep: `--demo -S not-a-date` returned a full report
with rc=1, which looked like missing validation until the real path showed rc=2 and a helpful
message. The flag was not unvalidated; it was ignored.

### Still open

* The badge/untracked-files item, unchanged.

## Round seventy-two — a substring check that could not fail, in the test guarding the 3.10 floor

2270 collected before, **2271** after (+1 net: one test split into two); `ruff`,
`ruff format` and `mypy src/ tests/` clean, and the only red is the documented badge test.

`test_the_one_backfill_there_is_is_declared` guarded the one thing that makes this package's
tests runnable on the floor it declares — `tomllib` is 3.11+, `requires-python` is `>=3.10`, and
the dev extra ships `tomli>=1.1; python_version < '3.11'` for it. It checked that with two
substring assertions, and **one of them cannot fail**:

    assert "import tomli as tomllib" in source     # `source` is THIS file

**Measured, not argued.** Breaking one of the two real fallbacks — replacing
`import tomli as tomllib` with `tomllib = None` inside the guard — left the class **passing, 3
of 3**. The phrase occurs four times in this file and two of those are the test's own machinery:
the assertion above quotes it, and `test_it_would_have_caught_the_one_that_shipped` embeds it in
an `ast.parse` fixture string. So the substring is satisfied by the code that checks it, and it
would go on being satisfied with every real guard gone.

Replaced with an AST check. `_tomllib_guards` walks each `try:` whose body imports `tomllib` and
reports whether any handler imports `tomli`, over `src/`, `tests/` and `tools/`. The marker
assertion is now tied to `ADDED_IN["tomllib"]` rather than matching the literal `< '3.11'`, so
the two numbers that must agree cannot drift apart independently.

Teeth, four neuters, each reddening exactly one test with 3 of 3 controls green:

| neuter | red |
| --- | --- |
| one real fallback broken (**the one the old version survived**) | the AST check |
| fallback imports `json` instead of `tomli` | the AST check |
| marker boundary bumped to `< '3.12'` | the marker check |
| marker line deleted | the marker check |

The second row is the case no substring check can reach at all: a handler that still imports
*something* keeps every phrase in the file intact.

**Found by generalising round seventy-one's own mistake.** The first draft of slurmate's
equivalent this round asserted `"tomli" in source.replace("tomllib", "")` and survived its
neuter for the same reason — two docstrings there say "``tomllib`` on 3.11+, ``tomli`` on older
Pythons" and "real TOML (tomllib/tomli)". Having watched a substring check pass on a broken
guard once, the sibling with the same shape was worth looking at.

### Still open

* The badge/untracked-files item, unchanged.

## Round seventy-one — nine `noqa` directives claimed a violation the line does not have

2262 collected before, **2270** after (+8); `ruff`, `ruff format` and `mypy src/ tests/` clean,
and the only red is the documented badge test.

Every other claim in this repo is checked by something. The **suppressions** were not, and this
is the one axis where that showed: `conftest.py`, `test_readability.py`, `test_tui.py` and
`test_ui_usability.py` carried **nine** `# noqa: E402` directives on imports that follow a
`sys.path.insert`, and ruff does not flag them. `E402` IS in `select` and `per-file-ignores`
for `tests/*` is `["ARG"]` only, so nothing was exempting them — each line simply advertised a
violation it does not have.

**All nine were BARE**, the code with no rationale after it, and that decided the treatment.
The same sweep across the family found stale directives in `nodetop` (2) and `rapidu` (5) where
every one carries a reviewer's note — `# noqa: S603 - fixed argv, never a shell`,
`# noqa: BLE001  (a hang is worse than a report)`, `# noqa: F401  (used in `# type:` comments)`.
Enabling this rule there would demand **deleting the note to satisfy the linter**, which is the
wrong trade, so it was not enabled there. Recorded rather than done.

**Measured on BOTH ends of the dev bound before removing anything.** The bound is
`ruff>=0.15,<0.17` and CI resolves the upper end; a directive one version calls unused can be
load-bearing on another. Installed 0.16.6 in a throwaway venv and re-ran: it agrees with the
local 0.15.18 on all nine, and on every repo's count (nodetop 2, rapidu 5, slurmwatch 2,
slurmate 0). The `select` comment two lines above records this spread biting once already —
0.16 surfaced 206 findings a local 0.15 run never saw — which is why the check was worth making
rather than assuming.

`RUF100` is now in `select`, so the **gate** keeps the directives honest and nothing in
`tests/` re-implements `ruff check`. What is pinned is that the rule stays selected, that no
BARE directive returns, and one end-to-end check that the rule fires on a planted file.

Teeth: dropping `RUF100` from `select` reddens **2** and the planted stale directive goes from
1 finding to **0**; all five controls green.
`tests/test_stale_suppressions_are_caught.py`, 8 tests.

**One of its tests guards only half the round**, and the neuter is what established that:
`test_no_bare_noqa_survives_in_the_tree` reddens if a bare directive comes back (the cleanup
half) and holds with `RUF100` dropped (so for the config half it is a control). Its docstring
says which.

**And the scanner had to exclude its own file** — it quotes the directive it searches for, in
the classifier and in a control. Third time that shape has bitten in this campaign.

### Still open

* The badge/untracked-files item, unchanged.

## Round seventy — the last three spellings of the confidence level now derive from `Z`

2253 collected before, **2262** after (+9); `ruff`, `ruff format` and `mypy src/ tests/` clean,
and the only red is the documented badge test.

Closes round sixty-nine's Still-open item, which is also the last of round sixty-eight's. That
item deferred three sites with a reason:

> `render.NODE_COLUMNS` declares a WIDTH beside the label (`Column("95% CI", 18, ...)`, and
> `render.table_floor` records that `NODE_COLUMNS` bottoms out at 41 cells), and `report.py`
> and `tui.py` key their row dicts BY that label, so all three must be one string. Rebuilding
> them is a layout change, not a polish one.

**The reason was about changing the label's TEXT, and deriving the same six characters changes
no layout — measured rather than assumed.** `render.CI_COLUMN = "%s%% CI" % CONFIDENCE_PERCENT`
is `'95% CI'`, the column is still 18 wide and right-aligned with `drop=1`, and
`table_floor(NODE_COLUMNS)` is still **41**. The `--plain --nodes` view is byte-identical
(md5 compared before and after). `render` already imported `MIN_SAMPLES` from `nodes`, so this
adds no dependency direction — and `nodes` still imports nothing from `render`, which is the
constraint that put the shared sentence in `nodes` in the first place.

**Why the KEY mattered and not just the header.** `text_table` looks each row's cells up BY the
column label, so a key that disagrees with the header does not raise — it renders the column
**empty**. Both new behavioural tests watch exactly that, and the drift neuter below proves it:
hardcoding `99% CI` at the three sites leaves the plain view and the dashboard with a blank CI
column and no error anywhere.

Teeth, two neuters, because the two failure modes differ:

| neuter | red | which half caught it |
| --- | --- | --- |
| three sites hardcode `95% CI` again | 1 | the source pin only — output is byte-identical |
| three sites hardcode `99% CI` | 4 | the table spec, BOTH surfaces' cells, and the source pin |

All controls green under both. `tests/test_ci_column_label_is_derived.py` (9), and round
sixty-nine's pin **inverted** in place: it used to assert `report.py` and `tui.py` each CONTAIN
the literal, which is now the thing that must not be true.

The dashboard test reads off the **compositor** (`screen._compositor.render_strips()`), the way
`test_requeue_tail_disclosure` reads a panel and `test_readability` pins as a rule — reading
`Static.renderable` returned an empty string here, because this screen keeps no `Text` of its
own and that attribute exists in textual 0.89 and not in 8.x.

### Still open

* The badge/untracked-files item, unchanged.
* Nothing else. Round sixty-eight's item is fully closed: the prose spelling derives (69), the
  three layout-coupled ones derive (70), and the two docstrings that quote `95% CI` as a worked
  example of a *format* are deliberately left alone.

## Round sixty-nine — the level `Z` decides, spelled by hand in the sentence both front ends share

2244 collected before, **2253** after (+9); `ruff`, `ruff format` and `mypy src/ tests/`
clean, coverage over the 75 floor, and the only red is the documented badge test.

Closes the half of round sixty-eight's Still-open item that could be closed without touching
layout. That item read: *"the level is literal text in six places while `Z` decides it ...
Raise `Z` and five sentences lie."* The six split into two kinds and they get different
treatment, which is the whole content of this round:

**Fixed — the prose.** `_note_from_row` builds the allocation note in `nodes.py`, which is
the one place both front ends share (`render` imports this module, and the analysis modules
may not import `render` — the function's own docstring says so). It carried a hardcoded
`95%% CI` inside its format string. Now `CONFIDENCE_PERCENT`, which is `"%g" % round(
CONFIDENCE_LEVEL * 100, 1)` — the same rounding as the `confidence_level` key the payload
carries, so the prose, the payload and the label cannot disagree about what `Z` means.
Rendering is **byte-identical** today, verified by capturing the sentence before and after
across both of its shapes (with a workload, and with the `over N placements` clause).

**Pinned, not rebuilt — the three layout-coupled spellings.** `render.NODE_COLUMNS` declares
a WIDTH beside the label (`Column("95% CI", 18, align="right")`, and `render.table_floor`
records that `NODE_COLUMNS` bottoms out at 41 cells), and `report.py:879` and `tui.py:2134`
key their row dicts BY that label, so all three must be one string. Rebuilding them is a
layout change, not a polish one. They are asserted against the derived value instead, so
raising `Z` now fails and names all three sites.

**Left alone — the two docstrings.** `duration.py:310` and `cli.py:503` quote `95% CI` as a
worked example of a format, not as a claim about this run's arithmetic.

**Teeth, and the first version of the pin was too narrow.** Two neuters, because the failure
modes differ:

| neuter | red | which half caught it |
| --- | --- | --- |
| sentence hardcodes `95` again | 1 | the source pin only — output is identical |
| sentence hardcodes `99` | 2 | source pin **and** the behavioural test |

The second row is why the pin changed. It first asserted `"95%% CI" not in source`, which
stayed **silent** under the drift neuter — the case the pin exists for. It now asserts
`re.findall(r"\d+%% CI", source) == []`, so any typed level fails. All four controls green
under both neuters.

`tests/test_ci_level_spelling_is_derived.py`, 9 tests. One of its controls is the quiet
branch: `verdict != "worse"` returns `""` before any formatting happens, so a healthy node
never reaches the spelling at all.

### Still open

* The badge/untracked-files item, unchanged.
* **The three layout-coupled spellings are pinned, not derived.** Raising `Z` now fails
  loudly and names them, which is the point; actually rebuilding the label from
  `CONFIDENCE_PERCENT` means re-deriving a declared column width and the two dict keys that
  match it, and `render.table_floor`'s 41-cell floor is asserted elsewhere. That is a layout
  change and wants its own round.

## Round sixty-eight — a confidence interval whose confidence level was not in the payload

2235 collected before, **2244** after (+9); `ruff`, `ruff format` and `mypy src/ tests/`
clean, and the only red is the documented badge test.

One defect, found by running the **rendered-vs-`--json` sweep** across all four text views
— the tactic that had been applied to two sibling packages and never to this one. Method:
take the same `--demo` history through both surfaces, then check that every integer the
rendered view prints is reachable from that view's own payload.

**The sweep needed a correction before it said anything true.** Its first pass reported ten
unreachable integers; nine were rounded renderings of stored floats, which the scan simply
could not see — the payload holds `core_hours: 105.29555555555555` and the table prints
`105`, so `105` looked absent. After crediting each float's roundings, `--overview`,
`--patterns` and `--sizing` came back **clean** and `--nodes` was left with exactly one:

    NODE                         N     RATE             95% CI VERDICT
                                                        ^^

**`--nodes --json` published `ci_low`, `ci_high`, `p_value` and `verdict`, and neither
threshold.** So a consumer held two interval bounds with no way to learn what level they
are an interval *of* — a 95% and a 99% interval are different claims about the same two
numbers — and a p-value beside a verdict with no way to learn which threshold produced it,
so it could neither re-derive the verdicts under its own alpha nor see how close a `same`
row came to tripping. `node_table` now carries `confidence_level` and `fdr_alpha`.

**`CONFIDENCE_LEVEL` is derived, not written down a second time.** The level is
`erf(Z / sqrt(2))`, which is 0.9500042 at `Z = 1.96`, so the payload cannot disagree with
the arithmetic that produced the interval. That matters here because the level is spelled as
literal text in **six** places — two of them column labels (`render.py:780`,
`report.py:879`, `tui.py:2134`, `nodes.py:899`, and two docstrings) — while `Z` is what
actually decides the interval. `tests/test_ci_level_is_published.py` holds the label and the
derived value together, which nothing did before.

Teeth: removing both keys reddens **4** tests, all 4 controls green. The derivation test
stays green under that neuter and says so in its own docstring — it guards against a
hardcoded `0.95`, which is a different question from whether the keys are published.

### Verified CLEAN this round — three withdrawals with numbers, do not re-run

* **The `--ascii` fold.** Measured with a vacuity guard in both directions, which is the
  half that makes it mean anything: `--overview` 3 non-ASCII characters without the flag and
  0 with it, `--patterns` 8→0, `--nodes` 3→0, `--sizing` 16→0, the default job view 21→0,
  `--failed` 19→0. Six views folded non-vacuously. (`--steps` emits no non-ASCII either way
  in `--demo`, so it proves nothing — recorded rather than counted.) `site.py:265`
  hardcodes a literal `\u2014` with no `ascii_mode` in scope, which is the exact shape of a
  leak found in a sibling package, and here it is harmless: `render.py:1203` folds the
  **finished text of each plain view**, and its docstring already says why that is the right
  place ("there is exactly one place per view where the text is complete").
* **Module-pair string literals.** All pairs across **19** modules share no prose literal at
  all — including the pairs a previous round listed as unswept (`nodes.py`, `diagnose.py`
  against `render.py`). The probe that found duplications in two sibling packages finds
  nothing here.
* **`sample_count`'s worked example.** `maxrss_sampling_note`'s docstring says an 89-second
  job at `JobAcctGatherFrequency=30` gets "at most three samples", which reads as an
  off-by-one against `89 // 30 == 2`. It is not: `sample_count` is `floor(e / f) + 1` and its
  own docstring says "3 for the 89-second job that prompted this, not 2", because the sampler
  gets one look at the start. A considered decision, documented at the site.

### Still open

* The badge/untracked-files item, unchanged.
* **The level is literal text in six places while `Z` decides it.** Round sixty-eight tied
  the `render.py` column label to the derived value; the other five spellings
  (`report.py:879`, `tui.py:2134`, `nodes.py:899`, and the two docstrings) are still
  hand-written. Deliberately not folded into this round: two of them are column labels whose
  WIDTH is load-bearing (`Column("95% CI", 18, ...)`, and `render.table_floor` records that
  `NODE_COLUMNS` bottoms out at 41 cells), so changing how they are built is a layout change,
  not a polish one. Raise `Z` and five sentences lie.

## Round sixty-seven — the requeue tail said how many workloads it hid, not what they cost

2213 tests before, **2235** after (+22); `ruff`, `ruff format` and `mypy src/ tests/` clean, and
the only red is the documented badge test.

`find_requeues` caps its findings at `REPEAT_REPORT_LIMIT` (4) and appends one summary for the
rest. That summary read `hidden` for `len()` and nothing else, so it published how MANY
workloads the cap dropped and withheld the one quantity the rule is *ranked* by — the abandoned
time, which each of the four findings above it prints for itself, and which the rule's own
docstring calls the figure that makes the case ("a requeued allocation really ran, and its hours
appear in no other total the tool prints").

This is the "container read, values dead" shape: `hidden` IS read, so a zero-reader sweep would
not have found it. Only the reads had to be classified.

### The byte-identical proof

Two histories differing only in the hidden tail's abandoned time, through
`find_requeues` on the tail finding's own evidence:

```
tail site OUT   00:09:00  -> sha 71a94bf6d290  'Shown in full with a narrower --since window.'
tail site OUT   3-00:00:00 -> sha 71a94bf6d290  'Shown in full with a narrower --since window.'
tail site IN    00:09:00  -> sha 74b6adef9bce  'The abandoned attempts ran 00:09:00 between them. ...'
tail site IN    3-00:00:00 -> sha 1f02eba3248a  'The abandoned attempts ran 3-00:00:00 between them. ...'
```

Nine minutes and three days were the same bytes. A reader deciding whether to spend a second,
narrower query had nothing to decide with.

### What changed

`patterns.py` gains `_abandoned_time_note(burned)` — one spelling, because the figure is now
reported twice (per workload, and for the tail) and the two must not word it differently. It
returns `""` for a zero or missing total, because an earlier attempt can end carrying no
`Elapsed` and "ran 00:00:00" reads as a measurement where there is none. The tail finding puts
the figure first and the instruction second, the shape `find_repeat_failures` already uses for
its own tail.

`render.py` cannot hold this sentence: it imports `rich`, and the analysis modules may not. So
the single spelling lives inside `patterns.py`.

### Provenance, and what I verified rather than took

This round was started by a subagent that hit its session limit mid-flight. Its last reported
line was "Now I'll apply the fix" — but it had already written both the change and a 22-test
file, which `md5sum -c` against the snapshot is what revealed. **The report and the tree
disagreed; the tree was right.** Verified here independently: the static gates, all 22 tests,
the byte-identical pair above (reproduced from scratch), and two neuters — the helper silenced
reddens 12, the tail site alone reddens 11, and no control reddens under either. The one-test
difference is the per-workload path, which the tail neuter does not touch.

### Still open

* The badge/untracked-files item, unchanged.

## Round sixty-six — FLAGGED counts runs, and the figure that says what they cost was read by nothing

2193 tests before, **2213** after (+20); `ruff`, `ruff format` and
`mypy src/ tests/` clean, coverage **96.34%** against the 75 floor, and the only red
is the documented badge test.

One defect, found by the sweep that has just paid off twice in slurmwatch: separate the
WRITES of every result-object field from its READS, and look for a value that is
computed, summed or parsed and then read by nothing.

**`GroupStats.wasted_gpu_hours` — declared `index.py:82`, summed `index.py:228`, read
nowhere.** It is the GPU-hours held by the runs the overview counts under FLAGGED. It
has been computed on every `build_groups` walk since the first commit (`11a5774`) and
its only other appearance in the tree was a `0.0` in one test fixture
(`test_index.py:404`).

FLAGGED is a run *count*, so it cannot carry the difference, and nothing else on the row
can either: `CPU / GPU-HOURS` is the workload's whole spend and `GroupStats.cost` — what
the list is ranked by — is a weighted sum of the same two totals. Two histories built to
agree on every dimension a surface showed and to differ only in the one it did not:

```
                 runs  completed  flagged  gpu_hours  core_hours   cost   wasted_gpu_hours
cheap failures     20         16        4      290.0      2320.0   6960                2.0
costly failures    20         16        4      290.0      2320.0   6960               90.0
```

Sixteen completed runs plus four FAILED, one card and eight cores each. In the first the
four flagged runs died in half an hour; in the second each held its card for 22.5 hours.
Rendered before the fix, `--plain --overview` came out **byte-identical** for both:

```
  window now-30days
  20 jobs in 1 workload · 80.0% completed
  ordered by compute used (1 GPU-hour = 16 CPU-hours) · "#" stands for a name's digits

  #    JOB NAME               PARTITION  RUNS COMPLETED  FLAGGED CPU / GPU-HOURS LAST RUN
  -----------------------------------------------------------------------------------------
  1    train-#                gpu          20        16        4   2,320 / 290   2026-08-20
```

So did the per-workload object in `--overview --json`, and `severity` and the rank agreed
too. 2 idle GPU-hours and 90 were the same output.

That matters because this module already calls idle GPU-hours the central finding, and
already reports them for the whole window: the summary above the table says "184
GPU-hours total, 91 of them never used" (`History.idle_gpu_hours`,
`render.idle_hours_note`). The reader's next question is *which workload* — and the answer
was being computed per group and thrown away. On the demo history the answer is the top
row: `node-evaluation` holds 84 of the window's 184 GPU-hours and **all 84 of them are
flagged**.

`--overview --json` is also the one hand-enumerated payload in the CLI, and it states the
rule this violated twice in its own comments — `distinct_names` is "off the table on
purpose ... but it is a real measurement, so it is emitted rather than lost", and the
failed/cancelled/noop breakdown "stays here so nothing measured is lost". Every other
payload escapes the question by going out wholesale (`history.stats`, `node_table(...)`,
`Advice._asdict()`, `Finding._asdict()`), which is why this was the only measured field
of `GroupStats` reaching no surface at all.

### The fix, on all three surfaces

* `index.py:558` — `History.idle_workload`, the workload holding the most idle GPU-hours,
  or `None`. Picked by the **absolute** figure, so "the most" is true; a two-hour workload
  wasting one of them must not outrank a 290-hour one wasting 90. Only then gated, on the
  pair `idle_gpu_hours` uses (`IDLE_SHARE_WORTH_NAMING`, `IDLE_HOURS_WORTH_NAMING`), read
  against the workload's own GPU-hours because that is the denominator the sentence
  prints. A CPU-only history is silent by construction.
* `render.py:1134` — `idle_workload_note`, one spelling for both front ends:
  `flagged runs held the most GPU-hours in train-#: 90 of its 290`. Both numbers, never
  the numerator alone — the slurmwatch lesson that started this sweep, where "idle cores
  240" read identically at 240-of-256 and 240-of-3200. Through `hours_text`, so a sliver
  reads `<1` rather than a rounded `0`.
* `report.py:707` — under the table, wrapped to the terminal. Not beside the total:
  `test_the_summary_is_brief` caps everything above the table at four lines on purpose.
* `tui.py:1103` — on the overview summary, its own line rather than a fifth `·` clause.
  The split in placement with one shared sentence is what `gpu_hours_equivalence` already
  does ("the caption on one surface, a help note on the other"); what must not differ is
  the wording, and now cannot.
* `cli.py:1289` — `"wasted_gpu_hours"` in the `--overview --json` workloads payload.

The dashboard placement took two attempts, and the suite caught the first: appended
among the summary's `·` clauses, the new line pushed `showing %d` onto a second line and
reddened `test_a_narrowed_table_still_reports_the_true_total`, which reads the narrowed
count off line one. That test was right and the placement was wrong -- `_summary`'s own
comment states the order ("the facts about the history come first, then what the view is
currently doing to them"), so the sentence now goes below both, and the reason is written
at the site.

Two frozen guards moved with it, which is what they are for: `render.py`'s public builder
count 48 → **49**, and its surface classification `both` 29 → **30**
(`test_render_surface_disclosure.py`). `idle_workload_note` is deliberately on both
surfaces.

### The tests and their teeth

`tests/test_idle_workload_disclosure.py`, 20 tests. Seven controls hold the *premise*
rather than the remedy and read nothing the fix added — the two histories agree on label,
partition, runs, completed, failed, problems, noop, cancelled, gpu_hours, core_hours,
severity, cost and last_seen; the table row, the hours cell and the FLAGGED cell are
still identical (no column moved); and a history whose waste is immaterial still says
nothing on either surface. With all three reader sites disabled — the exact pre-fix state
— **7 tests red, 13 green, and no control among them.**

Each site neutered on its own, one occurrence per file, verified before running:

| neuter | reddens |
| --- | --- |
| `report.py` never asks | 4, all plain or cross-surface |
| `tui.py` never asks | 2, dashboard and cross-surface |
| the JSON key removed | 2, both in the JSON class |
| `render`'s sentence replaced | 5, plain and dashboard, JSON untouched |
| the gate removed | 2, both "stays quiet" controls |
| the property returns `None` | 7 |
| `max` → `min` in the picker | 1 — the one test that plants a 100%-share sliver beside a 90-hour workload |

### The enumeration behind the pick

148 fields across the 8 `NamedTuple` result objects (`model.Step`, `model.Job`,
`model.Finding`, `model.Verdict`, `index.GroupStats`, `sizing.Advice`, `site.Site`,
`render.Column`). Five had no attribute read anywhere in `src/`. Four are benign and each
says so where it sits:

* `sizing.Advice.observed` — reached through `Advice._asdict()` on `--sizing --json`, and
  `report.py:1021` says exactly that: "`observed` is not dead -- it stays in the --json
  payload".
* `model.Verdict.job` — a handle back to the job a caller already holds, not a
  measurement.
* `index.GroupStats.kind` — `"gpu"`/`"cpu"`, and the GPU half of the hours cell already
  shows which a row is (`-` for CPU-only).
* `site.Site.accounting_storage_type` — parsed at `site.py:149` and read by nothing, but
  no figure or verdict in this tool turns on slurmdbd versus filetxt, so no reader loses
  anything.

The dict-shaped results all escape the question by being emitted whole:
`node_table`'s `comparison`, `direction` and `p_value` have no reader by name outside
`nodes.py`, and `goodput`'s `gpu_hours_completed`, `core_hours_total`, `noop_jobs`,
`gpu_goodput` and `gpu_noop_fraction` have none outside `patterns.py` — all of them go out
under `--nodes --json` and `"summary": history.stats` respectively.

### Still open

* **`History.gpu_concurrency` has no reader in `src/`, and a test docstring says it
  does.** `test_concurrency_still_available_to_callers`
  (`test_readability.py:256`) is headed "Trimmed from the display, not deleted -- it is in
  the JSON payload", and it is not: it is a `History` property, not a `stats` key, so no
  `--json` payload carries it. The test only asserts the property is not `None`, which is
  this suite's named failure mode — a test that asserts less than it appears to. Its
  helper `span_hours` feeds nothing else. Left for its own round: the fix is a decision
  about the JSON contract, not a one-line wiring.
* **`History.headline()`** — "One line for the footer: the number that should bother you
  most" — is called by six tests and by no surface. Same shape, same round.
* The badge/untracked-files item, unchanged.

## Round sixty-five — the classifiers understated support this package had already been run with

2184 tests before, **2193** after (+9); `ruff`, `ruff format` and `mypy src/ tests/`
clean, coverage **96.33%** against the 75 floor, and the only red is the documented
badge test.

`requires-python = ">=3.10"` has no upper bound, so pip already installs this on 3.14.
The classifiers stopped at 3.13 — which understates support rather than restricting
it, and classifiers are what PyPI shows and what tooling filters on.

**Not a guess for this package.** `issues.md` already records the published artefact
being installed from PyPI onto **midway2 — CentOS 7.9, glibc 2.17, Python 3.14.6,
Slurm 23.02, cgroup v1 — and exercised against that cluster's real accounting
history**, twice: round thirty-one's report against 0.7.0 and round thirty-six's
cross-cluster evaluation of 0.8.2. Neither reported an import or syntax failure; every
defect they filed was environment-general. A `Programming Language :: Python :: 3.14`
classifier is therefore a claim this repo's own record already supports.

Two tests hold it, transferred from slurmate, which has carried the identical pair
since the round its CHANGELOG describes ("the packages are 3.14-clean while their
classifiers stop at [3.13] ... nothing was blocked; the metadata simply understated
it"):

* every version `requires-python` allows is declared, and
* `test_no_removed_or_deprecated_stdlib_apis` — the thing that would actually break on
  a newer interpreter (`distutils`, `import imp`, `utcnow`, `getdefaultlocale`,
  `find_loader`, `pkg_resources`, `typing.ByteString`). `src/slurmpast` has none
  today; nothing was holding it there.

Both read `pyproject.toml` as **text, not through `tomllib`** — deliberately, and for
the reason slurmate's version records: `tomllib` is 3.11+, and 3.10 is the oldest
version these very tests assert support for, so importing it would make them
unrunnable on the interpreter they most need to run on.

**The CI matrix is deliberately not asserted.** It tops out at 3.13 because that is
what runners offer, which is a separate policy from what the package supports — the
same split slurmate keeps, and the reason a floor pin must not be copied between these
repos unexamined.

### How this round nearly went the wrong way

It opened as "slurmate has an anomaly": its classifiers list 3.14 while its matrix
stops at 3.13, and the two siblings agreed with their matrices. Reading slurmate's
CHANGELOG inverted it — the 3.14 entry is deliberate, already tested, and slurmate was
simply **ahead** of its siblings rather than out of step. The finding was in the two
repos that looked consistent.

### Still open

* The badge/untracked-files item, unchanged: 10 test files here are untracked. Since
  round sixty-four the failure says so itself.
* slurmwatch has neither of this round's two tests and no 3.14 evidence recorded, so
  the guard transfers there but the classifier claim does not.

## Round sixty-four — the standing badge failure now says which of two opposite causes it is

2174 tests before, **2184** after (+10); `ruff`, `ruff format` and `mypy src/ tests/`
clean, coverage **96.33%** against the 75 floor, and the only red is the badge test
itself — which is the point of this round.

`test_the_test_badge_matches_the_suite` compares the README badge against a live
`--collect-only`. Two opposite situations produce a mismatch:

* **the badge is stale** — tests were added and nobody bumped it. That is the case its
  own docstring records ("`tests-1029` sat in the README for two rounds"), and the fix
  is to bump the badge.
* **the tree holds test files that are not committed** — then the badge is *correct*
  for the suite that ships, the failure is expected locally, CI is green, and bumping
  the badge would **red CI**.

The message was `"README says N tests, the suite collects M"`, which cannot tell them
apart. This repo has been in the second state since round fifty-three, and the item has
sat in every Still-open list since — with each round re-deriving the explanation by
hand. Round sixty-one is the proof that the ambiguity costs something: I bumped the
badge to the live count to turn it green, which was backwards, and only measuring
`HEAD` caught it.

It now reads:

```
README says 1969 tests, the suite collects 2174 -- 9 test file(s) here are untracked
(tests/test_interval_spelling.py, tests/test_node_history_query_is_lazy.py,
tests/test_parse_cost.py, ...), which is exactly the difference: the badge states the
count of the suite that SHIPS, so it is correct for HEAD and this failure is expected
locally while CI is green. Commit or delete those files to close it -- bumping the
badge to 2174 would red CI.
```

Two helpers carry it, both in `test_layout.py`: `_untracked_test_files` (which returns
`[]` on any git failure, so a tarball install falls back to the plain "bump it" wording
rather than claiming a cause it cannot support) and `_badge_mismatch_reason`, whose
branches are pinned directly in `tests/test_badge_mismatch_diagnosis.py` — including
that a badge *ahead* of the suite is always "stale", since untracked files can only make
the live count larger. **The pass/fail semantics are untouched:** a genuinely stale badge
still fails, which is what CI relies on.

### One thing measured and dropped

I also meant to stop the badge test's nested `--collect-only` subprocess from leaving a
`.pytest_cache` behind, since it does not inherit the outer `-p no:cacheprovider`.
Measured: it leaves nothing. `--collect-only` writes no cache, so there was no defect —
whatever created the `.pytest_cache` seen in earlier rounds, it was not this.

### Still open

* The badge/untracked-files item itself, unchanged and not mine to close: 9 test files
  here are untracked, so committing or deleting them is the only thing that closes it.
  What changed is that nobody has to work that out again.

## Round sixty-three — the oldest open item had been closed, and the guard that closed it was untested

2169 tests before, **2174** after (+5); all four gates clean. One pin, plus a record
correction. No source change.

### The item, and the measurement that closes it

Every Still-open list from round fifty-three onward carried this, worded the same way:

> The note remains all but unreachable on `--plain` for a single job id, for round
> forty-eight's reason: `-j` loads only the records asked for, and changing that is a
> second `sacct` query.

`cli._node_history` does exactly that second query. It is wired at `cli.py:1338`,
computed once above both the `--json` and the plain rendering, and on the `-j` branch
it re-runs `_load` with `job_ids` cleared. Measured against this cluster rather than
read off the code -- a bare `slurmpast <id> --plain --no-logs` for a terminated job
with an allocation:

```
records from the bare id query:        1
population the note is computed from:  218
```

So the item is closed. This is the **third** stale entry found in two sittings (the
other two were slurmwatch's D19-era banked leads), which is now recorded in the loop's
memory as a rule: re-read the code before working a banked lead, because the note
outlives the tree.

### What that measurement turned up

`_node_history` opens with a guard whose only job is cost:

```python
if not any(expand_nodelist(job.node_list) for job in targets):
    return None
```

Its own docstring prices what it avoids -- "`-S now-30days` is 9.3 s for 13,075 rows"
-- and promises "nothing is queried unless some target job actually has an allocation
to say something about". `TestWhetherTheNodeNoteExistsAtAll` covers the widening
thoroughly, but **all three of its cases have an allocation**, so none can see the
guard. Verified by neuter, not assumed: with the guard deleted all three still pass --
they simply get a population they already wanted -- while every `slurmpast <id>` pays
a second query it can do nothing with.

`tests/test_node_history_query_is_lazy.py` counts window queries through a fake Slurm
that answers `-j` with one row, and pins zero of them for a `NodeList=None assigned`
job (cancelled before it started -- an ordinary shape, not a contrived one). Its
controls take the allocated path, which the guard cannot reach, so they hold either
way.

Two fixture mistakes worth recording, both mine, both caught by running it:
`parse` reads raw `|` and only the fake runner's *output* carries `SAFE_DELIMITER`,
so parsing the pre-encoded text yielded zero jobs; and the note is a COMPARISON
("against 0.0% on every other node"), so a single-node fleet produces no note at all
and the control that asserted the note was meaningless until a clean node was added.

### Still open

* The badge/untracked-files item, unchanged and not mine to close: the README states
  the count of the suite that SHIPS (1969 at `HEAD`) and eight test files here are
  untracked. Committing or deleting them closes it.

## Round sixty-two — a test that asserted an exit code the report owns

2169 tests, unchanged; all four gates clean. No source change: this fixes a test of
mine that was going to go red on someone eventually, and did.

`test_portability_round81.py::TestADroppedFlagIsReported` shells out to the real tool
and asserted:

```python
rc, err = self._stderr("--no-logs", "--log-dir", "/tmp")
assert "--log-dir has no effect with --no-logs" in err, err
assert "/tmp" in err
assert rc == 0, "a dropped flag is a warning, not a failure"
```

The first two hold. The third does not belong to flag handling at all: `cli.py:1438` is
`return 1 if worst_critical else 0`, so **the exit code carries the report's verdict**.
On a week whose history holds a critical finding the tool exits 1 having printed a
perfectly good report -- which is the documented design, not a defect.

So the test passed for weeks and then failed, with nothing in this package having
changed. Measured while diagnosing it: 186 jobs in the default window, `rc=1` from
`slurmpast --no-logs` with no other flags, the full report rendered correctly above it.

### Two wrong turns worth recording, because both looked like answers

1. **"It's the known flake."** It is not: the same case failed **3/3 in isolation**,
   while the round81 cases that flake are the signal/terminal-restore ones. The tell was
   that this test's name is about a flag message, not a terminal. A different test failing
   in the same file is not evidence of the same cause.
2. **"The tool exits 1 on a good report -- that's the bug."** My first probe piped to
   `head -3`, which closes the pipe, so `rc=1` could have been EPIPE from my own probe.
   Re-run without the pipe: still 1, and the reason is the verdict above. Neither the
   tool nor the flag handling is at fault.

### The fix

The claim is "a dropped flag changed nothing", so the test now says that, against the
same invocation without the dropped flag:

```python
baseline, _ = self._stderr("--no-logs")
assert rc == baseline, (rc, baseline)
```

Immune to the caller's job history, and still has teeth: making the warning path
`return 3` reddens this case and leaves the class's other three green -- including
`test_either_flag_alone_is_silent`, which is that class's own control. (The first
attempt at that neuter inserted a line by paren-walking and produced a `SyntaxError`,
which failed all four in 0.57s instead of the usual 9s. A neuter that does not parse
reads as teeth and is not; check that the file parses and that the timing is plausible.)

### Still open

Nothing new. The badge failure remains the expected one -- the README states the count
of the suite that SHIPS (1969 at `HEAD`), and eight test files here are untracked.

## Round sixty-one — the module that exists to stop drift did not say where nine of its own builders belong

2161 tests before, **2169** after (+8 here); all four gates clean. One change, plus a
badge reverted to the value the recorded rule asks for -- see the last section.

`render.py` exists so the dashboard and `--plain` cannot drift: a fact is spelled
once and both surfaces read that spelling. Whether that holds depends on a reader
being able to tell a *deliberate* single-surface builder from one nobody wired up
yet, and the only place that intent can live is the docstring.

Measured, import-aware, across the forty-eight public functions:

| reached by | count |
| --- | --- |
| both surfaces | 29 |
| `--plain` only | 5 |
| dashboard only | 8 |
| neither (helpers called inside `render.py`, or by tests) | 6 |

Round fifty-six's entry records that each single-surface builder's docstring says
which surface it belongs to. **It did not.** Five public functions had no docstring
at all -- `health_dot`, `state_text`, `severity_chip`, `sort_findings`,
`register_alignment` -- and four more were documented but silent about surface:
`hours_pair_text`, `severity_tag`, `nothing_matches`, `search_hint`. Nine of
forty-eight. All nine now say it, and `tests/test_render_surface_disclosure.py`
pins all three claims: no public function is bare, every single-surface builder
names its surface, and the 29/5/8/6 split is frozen so a builder crossing surfaces
is a decision rather than a diff nobody saw.

### A hypothesis withdrawn, and the measurement that killed it

The first explanation was structural and wrong: `report.py` neither imports nor
constructs a rich `Text`, so "returns a `Text`" looked like it *forced*
dashboard-only. But two of the six builders touching `Text` -- `bar` and
`resource_rows` -- are in the both-surfaces set, and `report.py:330` shows why:

```python
prefix = bar(gauge, "", width=DETAIL_BAR_WIDTH, ascii_mode=ascii_mode, flat=True).plain
```

The plain renderer reads `.plain` off a `Text` wherever sharing is wanted. So no
builder is dashboard-only *because* of its return type, and the docstrings now say
the split is a pairing decision -- `severity_tag`/`severity_chip`,
`hours_pair_text`/`hours_pair`, string half and coloured half -- which a future
caller on the other side may revisit.

### The trap in the checker, recorded because a first cut shipped it

A first cut counted every `ast.Name` matching a builder and reported `bar_cells` as
called by the dashboard. It is not: `tui.py:1795` has a **local variable** of that
name, passed to `pair_value_budget(width, bar_cells=...)`, and nothing calls the
builder outside `render.py`. Resolving each surface by how it actually imports --
`tui.py` does `from . import render` and calls `render.X`; `report.py` does
`from .render import (...)` and calls bare -- reproduces 29/5/8/6. `TestControls`
pins that behaviour against planted synthetic source, so it measures the resolver
rather than today's call graph, and holds whatever the docstrings say.

### One thing checked and found already right

`nothing_matches` explains an empty table and names the key that undoes it, and it
is dashboard-only -- so: does `--plain` have the bare-header-over-blank-space
failure it was written to prevent? `--plain` does filter (`-p`, `--failed`), but an
empty result there never reaches a table. `cli.py:408` raises first and names both
the filter and its value:

```
slurmpast: no jobs for youzhi since now-7days matching --partition nosuchpartition
slurmpast: no demo jobs match partition nosuchpartition          # cli.py:355
```

No gap; the reason is now in the docstring instead of being rediscovered.

### The badge, and why bumping it was the wrong instinct

`test_the_test_badge_matches_the_suite` collects the **live** suite, so it fails in
any working tree holding untracked tests -- eight of them here. The instinct was to
bump the badge to the live count and turn it green. That is backwards, and measuring
`HEAD` is what showed it:

| | badge | suite collects |
| --- | --- | --- |
| `HEAD` (what ships, what CI runs) | 1969 | **1969** |
| working tree before this round | 2034 | 2169 |

CI is green because `HEAD` agrees with itself. The working tree's 2034 agreed with
nothing -- neither the committed suite nor the live one -- and was drift from an
earlier round. Setting it to 2169 would have been right only if every untracked test
file were committed in the same commit as the README; three of them
(`test_parse_cost.py`, `test_portability_round81.py`, `test_subprocess_text_mode.py`)
have stayed untracked for many rounds.

So the badge is back to **1969**, byte-identical to `HEAD`: the README ships with the
package and states the count of the suite that ships with it. The local failure of
this one test is the expected cost of that and is not a defect. **Whoever commits the
untracked tests bumps the badge in the same commit**, to whatever the tree then
collects (2169 today).

### Still open

Nothing new. The known flake class is unchanged and is not a defect in this package:
`test_portability_round81.py`'s signal/terminal-restore cases fail intermittently
under full-suite load -- confirmed this round by md5 (the file is untouched) and an
isolated re-run, which reddened a *different* case in the same class while the two
that failed in the full run passed.

## Round sixty — an open item that had already been closed

No code changed. 2034 tests before and after; all four gates clean. This round is a
correction to the record, and the error was mine: round fifty-nine's Still-open list
carried an item that round **fifty-five** had already fixed.

### The item, and the proof it is closed

Round fifty-nine listed, as untouched:

> Round forty-eight's third item: one-sided p-values chosen after seeing the
> direction, pooled into one BH family with the opposite direction's. A statistical
> question, not a labelling one.

Round fifty-five's own entry opens by saying it "closes the **oldest** item in the
Still-open list: round **forty-seven's second**", and quotes that item verbatim:

> **One-sided p-values chosen after seeing the direction**, pooled into one BH
> family with the opposite direction's.

Word for word the same item, attributed to a different round. Verified in the code
rather than taken from the entry:

* `nodes.selected_direction_p_value` exists (`nodes.py:292`) and is documented as
  ":func:`node_p_value`, priced for a ``direction`` that was read off the data";
* it is **wired** — `nodes.py:520` computes each row's `p_value` through it;
* raw `node_p_value` is reached from exactly one place, `nodes.py:313`, which is
  inside the priced wrapper and doubles the tail. No caller gets the unpriced value.

So the deferral is spent and the entry was wrong to carry it. Corrected in place
above with a pointer here.

### Two things checked while verifying it, both clean

* **The per-job note and the node table cannot disagree about the statistics.**
  `note_for_allocation` does not compute its own p-value; it calls
  `node_table(...)` and reads the row, which is what its docstring requires ("the
  family the correction is applied over has to be the table, not a per-node slice
  of it"). Pricing the direction therefore reached both surfaces at once.
* **`--metric` not reaching the per-job note is not a drift.** The note hardcodes
  `metric="failure"` while `--metric` defaults to `hang`, but `--metric`'s help says
  "what **--nodes** measures", and each surface names the metric it used. Different
  commands, each self-describing.

### Still open

* The note remains all but unreachable on `--plain` for a single job id, for round
  forty-eight's reason: `-j` loads only the records asked for, and changing that is a
  second `sacct` query.
* The badge/untracked-files item: the local suite collects 2160 against a committed
  2034, because `test_parse_cost.py`, `test_portability_round81.py` and
  `test_subprocess_text_mode.py` are untracked. Committing or deleting them closes
  it; flipping the badge reds CI.

## Round fifty-nine — the sizing surface the dashboard said nothing about

Two fixes, both from round fifty-seven's Still-open item ("The overview, the job
list and `--sizing` still have no end-to-end routing test"). 2021 tests before,
**2034** here; all four gates clean.

### Working the item first CORRECTED it: two of its three are not gaps

Measured, not argued:

* The **overview** does have an end-to-end pairing —
  `test_ui_usability.py::test_both_surfaces_say_the_same_thing` asserts the idle
  clause is in `render_overview(...)` **and** in the dashboard's `summary_text`.
* The **job list** has no shared sentence to route. `report.render_list` calls
  exactly `cores_text`, `stamp_short` and `text_table` — all formatting. There is
  nothing for a routing test to route.
* **`--sizing` is the real one**, and its prose lives in `sizing.py`, which as an
  analysis module may not import `render`; both front ends import `recommend` from
  it, so the sentences are single-sourced. The fields that carry them are
  `Advice.basis` and `Advice.caution`.

Two measurement traps on the way, both of which first read as live defects:

* An exact-substring comparison reported `caution` **missing from `--sizing` for 8
  of 10** advices. It is not: `render_sizing` wraps to `_plain_width()`. Compared
  on the words — this file's rule since round fifty-six — everything matched.
* `Advice.observed` really is absent from both text surfaces, and that is correct:
  it is the DATA behind `basis` (`1.9 GiB peak across 6 runs` against `the most any
  run used was 1.9 GiB.`), not a second sentence. `--sizing --json` is where a
  consumer reads the field. Pinned with the reason so a later sweep does not "fix"
  it into both surfaces and say the same thing twice.

### The finding: a `capped` workload appeared on NO screen

`Advice.actionable` is `verdict in ("raise", "lower") and bool(suggestion)`, and the
banner filtered on it — so a **`capped`** verdict was dropped from the dashboard
entirely while `--sizing` gave it a flag line, its basis, and the caution that names
the way out. `sizing.py:524` gives `capped` its own verdict for a stated reason:

> Clamping alone turned "raise to 34" into "already about right", which is a
> different wrong answer: the workload is using 27.9 of its 28 cores and would take
> more.

So the one surface that said nothing was the default one. Measured with the demo
history against a pinned 2-core ceiling — three workloads capped, `--sizing` naming
all three and the banner none:

    midtrain  --cpus-per-task  --sizing: flag=True  caution=True  | dashboard: flag=False caution=False

`--demo` pins `{"test": (48, …)}` and the demo's busiest workload uses 7.5 cores, so
nothing is ever capped there — which is exactly why the branch had no coverage on
either surface. My first probe read `history()` with **no** ceiling pinned at all,
where `partition_ceiling` returns `(None, None)` and capping cannot happen; that
looked like "unreachable" and was a wrong measurement, not a result.

The fix is in two parts because the label is a sentence both surfaces now draw, and
this repo's rule puts those in `render.py`: `render.capped_label()` owns
`at this partition's ceiling`, `report` routes through it, and the banner includes
capped items using it. The clamped `suggestion` is deliberately **not** rendered as
`--cpus-per-task=2` on either surface — that reads as advice to shrink, which is the
"different wrong answer" the verdict exists to avoid. `sizing.sbatch_lines` already
filtered on `actionable`, so no pasteable line was ever emitted for one.

Teeth, four neuters: dropping `caution` from the banner and dropping it from
`--sizing` each redden only `test_the_caution_is_on_both` (so the pin guards both
surfaces, not one); restoring the actionable-only filter reddens only
`test_the_ceiling_line_is_on_both` with 8 controls passing; and re-spelling the label
in `tui.py` reddens only `test_control_the_label_has_one_home`, which is what makes
that control load-bearing.

### Corrections to older records

* **Round fifty-eight's Open item is CLOSED as unreachable.** It recorded
  `format_rate_range(0.9996, 1.0)` reading `"100.0 – 100.0%"` as "the same defect one
  helper over". Nothing can produce that pair: the ends come from
  `nodes.wilson_interval(bad, trials)`, whose lower bound enters [99.95%, 100%) only
  at **n ≳ 10,000 placements on one node** (n=5000 gives `99.9 – 100.0%`), and the
  heaviest single node for a heavy user over 90 days on this cluster is **715
  placements** out of 15,022 rows. Do not re-open without a placement count two
  orders of magnitude larger.
* The badge item's figures were stale in every round that carried them forward. The
  local suite now collects **2147** against a committed **2034**; the three untracked
  files are unchanged, and so is the conclusion (committing or deleting them closes
  it; flipping the badge reds CI).

### Still open

* The note remains all but unreachable on `--plain` for a single job id, for round
  forty-eight's reason: `-j` loads only the records asked for, and changing that is a
  second `sacct` query.
* ~~Round forty-eight's third item: one-sided p-values chosen after seeing the
  direction.~~ **Stale when this list was written — round fifty-five closed it.**
  See round sixty.
* The badge/untracked-files item above.

## Round fifty-eight — `format_percent` named a boundary it had not reached, and here the boundary is a claim

One fix, in `duration.py`. 1995 tests before, **2021** here; all four gates clean.
Found by the rule this module states about itself twice and this function did not
follow: `format_bytes` says "the unit is chosen for the value as PRINTED, not as
stored" and keeps `_ROUNDS_UP_AT` to enforce it, and round fifty-two fixed
`format_duration` for exactly this (59.95s printing "60.0s"). `%.1f` flips to
`100.0` at 99.95 and to `0.0` anywhere below 0.05.

### Why a percentage boundary is worse than a byte one

`1024.0 MiB` is a ladder failure a reader can still act on. Both ends of a
percentage are read as statements about whether anything happened, and three
callers put them next to a word that makes the claim explicit:

    report.py:533   format_percent(stats["completion_rate"]) + " completed"
    tui.py:1053     the same line on the dashboard
    render.py:1393  format_percent(job.walltime_used)

Measured rather than argued:

    2000 jobs, 1 failure  -> rate 0.999500 -> "100.0% completed"
    5000 jobs, 1 failure  -> rate 0.999800 -> "100.0% completed"
   13051 jobs, 1 failure  -> rate 0.999923 -> "100.0% completed"

2000 is where it starts, and 13,051 is the real parent-job count a 30-day window
holds on this cluster — so this is the ordinary scale, not a corner. The tool whose
job is to say what failed was telling the reader nothing had.

The low end is the function's own docstring one step in. It already refuses `0%` for
a missing reading ("printing ``0%`` for a failed read is indistinguishable from a
real measurement of zero") and then printed `0.0%` for a real 0.0077% — one failure
in 13,051 — so that one string meant "none" AND "some, but under a tenth". And
`walltime_used` at 99.96% printed "100.0%" for a job that did not hit the wall,
which is the distinction a TIMEOUT diagnosis turns on.

### The fix, and why a bound rather than more precision

An interior value now gets a BOUND: `<0.1%` and `>99.9%`. Printing `0.1%` for
0.0077% would invent a factor of 13. The spelling is not new to this family —
`rapidu.fmt` returns `<0.01x` and `nodetop.core.duration` returns `<1m` for the same
"nonzero but below the resolution" case — so this is consistency, not a new
convention. `>99.9%` is six characters, which is exactly the `MEM%` column width.

**The exact boundaries still print as boundaries.** 0.0 is `0.0%` and 1.0 is
`100.0%`, because those are true, and two tests already pinned them
(`test_duration.py:140`, `:191`). Only the strictly interior band moves. Above 100%
is untouched — MEM% legitimately reads `102.6%` for a job that exceeded its request
— and so is anything negative. No existing test changed: the interior band was
covered by nothing, which is how it survived.

Teeth: with both branches removed, 10 tests redden (nine formatter cases and the
end-to-end "100.0% completed" line) while all fifteen controls and the vacuity guard
pass in both states — including `test_control_a_genuinely_all_completed_window_still
_says_so`, so the fix demonstrably did not swallow the true case.

### Open — the same defect one helper over, NOT fixed here

`format_rate_range(0.9996, 1.0)` reads `"100.0 – 100.0%"`: an interval of
[99.96%, 100%] presented as a degenerate one. It builds its own `"%.1f – %.1f%%"` and
does not call `format_percent`, so this round could not reach it and deliberately did
not extend into it — a range shows both ends, so it needs its own decision about
whether `">99.9 – 100.0%"` reads better than widening the precision, and `ci_range`'s
spelling is pinned in three places. Recorded rather than pinned:
`test_percent_boundary.py` asserts only that the shared helper still answers, with a
comment saying why the wrong string is not written into an assertion.

### Numbers a reader might be depending on

`--json` is unaffected (it carries fractions, not formatted strings). On the text
surfaces, a completion rate in [99.95%, 100%) now reads `>99.9%` instead of
`100.0%`, and a nonzero share below 0.05% reads `<0.1%` instead of `0.0%`.

## Round fifty-seven — the exclude block's quiet branch, and a control that measured the runner's TMPDIR

Two fixes, both in the test suite: nothing shipped in `src/` changed. 1993 tests
before, **1995** here; all four gates clean. Round fifty-six's own record named the
lead ("end-to-end routing tests existed for two screens of six"), and working it
first produced a **correction to that framing**, which is recorded here because the
wrong version of it would have bought three redundant assertions.

### The cross-surface hunt came up clean, and that is the result

Both surfaces were driven at every screen — overview, job list, workload, job,
patterns, nodes — and their prose compared two ways: line-keyed on words (the
round fifty-six rule), and again wrap-insensitively on 6-word shingles, since the
dashboard wraps to its panel and `--plain` to `_plain_width()` and a line-keyed
diff reads a different line break as a different sentence.

**No drift was found.** Every apparent difference resolved to one of three things
that are not drift, each already reasoned about in the code:

* Chrome. The dashboard's title row and its key-binding footer; `--plain`'s caption.
* The overview caption. `ordered by compute used (1 GPU-hour = 16 CPU-hours) · "#"
  stands for a name's digits` is `--plain`-only on that screen, and the two facts
  are under `?` on the dashboard — phrased for the medium, which is why a shingle
  match does not find them and why looking only at the overview screen suggests a
  gap that is not there. `report.py:619` states the arrangement outright.
* The sort. `--plain` always names the ordering; the dashboard names it only when
  it is not the default, and `tui.py:1008` gives the reason ("a bare 'everything'
  is noise, and so is 'by resource use' on the default ordering"). `report.py:622`
  cites the dashboard's behaviour as the correct one.

Also checked and clean: the four public no-arg builders that neither front end
calls (`mem_text`, `exit_pair_text`, `requeue_summary`, `register_alignment`) are
each called from inside `render.py` by `job_sections`, so both surfaces do reach
them — not dead code. And the job list's missing `NODE` column is `fit_columns`
doing its job: `Column(label="NODE", drop=4)` appears at width 120 and above, and
both surfaces drop in the same declared order.

### The finding: only the FLAGGED half of the exclude block was drawn end to end

`tests/test_tui.py::TestTheDashboardDrawsTheSharedSentences` covers the nodes
screen when a node IS worse — disclaimer, correction note, workload control — and
it has real teeth: with `render.nodes_exclude_disclaimer()` left called but its
output replaced by `""` at `tui.py:2119`, that test reddens.

Its `else` was not covered. `render.nodes_nothing_to_exclude()` — "no node is
worse than the rest; nothing to exclude." — was asserted on `--plain` only
(`test_audit.py:612`), and it is the branch a **healthy** cluster takes every
time. Neutered the same way at `tui.py:2134`, four tests were consulted and three
were content:

    test_the_plain_renderer_emits_the_shared_sentences_verbatim   passed
    test_no_sentence_is_written_out_in_both_front_ends            passed
    TestTheDashboardDrawsTheSharedSentences                       passed
    test_the_dashboard_draws_the_quiet_half_of_the_exclude_block  FAILED  (new)

So a healthy fleet's verdict could have stopped reaching the dashboard with the
suite green. The reader told nothing is wrong is exactly the one who cannot tell a
clean verdict from a panel that failed to draw.

The route is pinned with it. On a uniform fleet that branch is reached only under
the **failure** metric and the nodes view opens on `hang`, so the test presses `m`
— and asserts the sentence is *absent* before that press, so the key cannot become
unnecessary and leave the assertion passing off the other branch. A second, cheaper
pin came with the harness: `patterns_empty()` on a history of **zero** jobs, where
every upstream count is 0, rather than on the demo's healthy subset the existing
test uses.

### The second fix: a control whose verdict depended on `$TMPDIR`

`TestTheInferredLogHedgeIsOneSentenceInOneHue::
test_the_other_half_of_the_same_branch_was_already_shared` compares
`render.log_miss_detail(job)` across both surfaces. That sentence **embeds an
absolute path**, and pytest builds `tmp_path` under `TMPDIR`, so the runner chooses
its length. Under a ~100-character temp root the sentence reached 150 characters,
the hardcoded 120-cell panel dropped its tail, and the control failed — while
`--plain`, which wraps rather than clips, still passed. Measured both ways:

    TMPDIR=/project/.../scratchpad/gate_slurmpast   1 failed
    TMPDIR unset (/tmp)                             1 passed

Clipping is correct — the docstring itself grants each surface its own prose width
— so the defect is the assertion, which was measuring the temp directory. `_dashboard`
now takes a `width`, and the call passes `max(120, len(detail) + 20)`. With the
parameter reverted the split above returns exactly; with it in place both roots
pass. No `src/` behaviour is involved, and this is the kind of failure that reaches
a contributor as a mystery rather than as a bug.

### Numbers a reader might be depending on

None moved. Both fixes are tests; `src/` is byte-identical to round fifty-six, which
was verified by md5 rather than asserted.

## Round fifty-six — the log-line `if` was shared, the `elif` above it was written twice

Two fixes, both in the seam `render.py` exists to close, found by asking the
question the other way round: not "which sentences did we move to `render`?" but
"which prose in `report.py` or `tui.py` is still written out there?". 1986 tests
before, **1993** here; all four gates clean.

### The coverage that was already there, measured

`render.py` has 47 public builders after this round. Walking the call graph of both
front ends over all of them gives this: **28 are called by both surfaces**; **13 by
exactly one** — `ascii_fold`, `severity_tag`, `hours_pair_text`, `text_table`,
`wrap_or_clip` on the plain side, `clip`, `health_dot`, `severity_chip`,
`state_text`, `sort_findings`, `search_hint`, `nothing_matches`, `hours_pair` on the
dashboard's, each single-surface by design and each docstring saying which
(`ascii_fold`'s at length: "Deliberately NOT applied to the dashboard") — and **6
by neither**, of which five are internal to `render` (`bar_cells`,
`exit_pair_text`, `mem_text`, `requeue_summary`, `register_alignment`) and
`table_floor` is read only by tests and comments.

End-to-end routing tests existed for **two screens of six**:

* `test_audit.py::TestTheTwoSurfacesCannotDriftApart::
  test_the_plain_renderer_emits_the_shared_sentences_verbatim` — nodes, patterns.
* `test_tui.py::TestTheDashboardDrawsTheSharedSentences` — nodes, patterns.

The job screen, the overview, the job list and `--sizing` had no such test. What
covered them instead was the source sweep, `test_no_sentence_is_written_out_in_both_
front_ends`, and that is where the hole was.

### 1. The hedge on a log matched by timing was maintained in two files

`report.py:392` and `tui.py:1859`, before this round:

```python
# report.render_job
note = "(matched by timing, not by name — verify before trusting it)"
...
out.append("  %s %s  %s" % (style("log", "grey"), log_path, style(note, "grey")))

# tui.JobScreen.render_body
body.append(
    "       matched by timing, not by name — verify before trusting it\n",
    style=theme.HEALTH_COLOR["warn"],
)
```

One sentence, two files, no test on either copy — and it is the **`if` half of a
two-branch decision whose `elif` was fixed and tested three rounds' worth of work
ago**. `render.log_miss_detail` has owned the "no log found" line since round
thirty-three, with a cross-surface test *and* a control
(`test_portability.py:4401`). The branch immediately above it kept two copies. The
comment on the fixed branch even says "the same one `--plain` prints --
`render.log_miss_detail` holds the rule for both", eight lines under a line that
did not.

**It is the ordinary case, not a corner.** Over `sacct -u youzhi -S now-30days` on
midway3 — 13,051 parent jobs — **469 resolve their log by timing rather than by
name**, because the scripts that wrote them number their output (`report/<N>-train.out`)
instead of naming the job. Every one of those 469 post-mortems draws this line.

**The visible half of the drift is the hue.** `logs.find_log_by_time` states the
stake in its own docstring — *"it is still an inference either way, so callers must
label it as one: a wrong log invents a cause, which is worse than no log"* — and
the dashboard drew the line in `HEALTH_COLOR["warn"]` accordingly. `--plain` drew
it `grey`: the hue this module uses for bookkeeping, and the hue of the word `log`
two cells to its left. The one sentence on the screen warning that the traceback
below it may belong to a different job was the quietest thing on it, on the surface
that gets pasted into tickets.

Both surfaces, same job, same window, after the fix — job `53074942`, whose log
`/home/youzhi/ArgonneAI/report/a4_pcanchor.out` carries neither its id nor its name:

```
$ COLUMNS=140 slurmpast 53074942 --plain -S now-30days
  log /home/youzhi/ArgonneAI/report/a4_pcanchor.out  (matched by timing, not by name — verify before trusting it)

$ COLUMNS=80 slurmpast 53074942 --plain -S now-30days
  log /home/youzhi/ArgonneAI/report/a4_pcanchor.out
      matched by timing, not by name — verify before trusting it
```

```
# tui.JobScreen at the same id, through Textual's run_test(size=(140, 50))
DASH 31|    log  /home/youzhi/ArgonneAI/report/a4_pcanchor.out
DASH 32|         matched by timing, not by name — verify before trusting it
```

The fix is `render.log_inferred_note()` (`render.py:195`), called from
`report.py:404` and `tui.py:1864`, and `--plain` now says it in the hue this module
already spells the dashboard's warn as. The parentheses stay where the note rides
on the path's line and come off where it gets a line of its own — that is layout,
it is a distinction `report` was already making (`note.strip("()")`), and it is
what keeps the aside legible with colour off. The only layout the dashboard has is
the second one, and there the two surfaces are now byte-identical.

### 2. The sweep that forbids exactly this could not see it

`test_audit.py:505`, before:

```python
value = node.value.strip()
if len(value) >= 25 and " " in value and "\n" not in value:
    found.setdefault(value, []).append(node.lineno)
```

Three separate reasons that pair got through. It keyed on the **literal, byte for
byte**, so `(matched by timing…)` and `matched by timing…` were two unrelated
strings; it **skipped anything holding a newline**, which the dashboard's copy did;
and its floor was **characters, not words**, which admits `"    %-17s %s %s   %s"`
and excludes `"nothing to flag."`.

The key is now the words — lowercased, punctuation and padding and line breaks
discarded — past a floor of three of them. Below three the matches are `Column`
keys (`WALL TIME`, `PEAK MEM`, `JOB NAME`), which legitimately appear in both front
ends because they *are* the lookup into a spec `render` owns, and Slurm directives
(`#SBATCH --exclude=`), which are what the reader types rather than something this
package phrases.

Turning it on named two more copies, both now routed rather than exempted:

* `"nothing to flag."` — the whole findings block when `diagnose` returned none,
  written out at `report.py:444` and `tui.py:1879` before this round (`report.py:464`,
  `tui.py:1884` now). Now `render.NOTHING_TO_FLAG`.
* `"ABOVE THE LIMIT"` — built by `render.job_sections` into the `peak (MaxRSS)`
  value and then **searched for** by `report.render_job` and `tui.JobScreen` with
  `"ABOVE THE LIMIT" in value`, to paint that row in the alarm hue. Three literals
  in three files, and the one keeping the red on the row that says a job blew its
  own memory ceiling. Nothing would have failed if `render` had rephrased its own
  note; the row would simply have stopped being red on both surfaces at once,
  silently. Now `render.OVER_LIMIT_MARK`.

### The tests, and the controls

`tests/test_audit.py:617`, `TestTheInferredLogHedgeIsOneSentenceInOneHue`, plus two
new controls on the sweep in `TestTheTwoSurfacesCannotDriftApart`. Both surfaces are
driven against one job whose log is reachable *only* by mtime — the fixture asserts
`inferred is True` rather than assuming it, because a fixture that hands back a
name match tests nothing.

Failing before and passing after, verified by restoring the two hand-written copies
and nothing else (3 failed, 7 passed):

* `test_no_sentence_is_written_out_in_both_front_ends` — `duplicated between
  report.py and tui.py: 'matched by timing not by name verify before trusting it'
  (report.py:[404], tui.py:[1864])`.
* `test_the_plain_hedge_is_in_the_warning_hue` — `'\x1b[90m' == '\x1b[33m'` fails.
* `test_the_hedge_stays_shared_when_it_gets_its_own_line` — the same, at the width
  that pushes the note onto its own line, so the fix is not width-dependent.

Restoring only the two companion copies reds the same sweep with `duplicated
between report.py and tui.py: 'above the limit' (report.py:[297], tui.py:[1813]);
'nothing to flag' (report.py:[462], tui.py:[1884])`.

**The expectation is not read out of the code under test.** "The warning hue" comes
from the *overview's* idle clause: `report.render_overview` styles
`render.idle_hours_note` one way and `tui.OverviewScreen` styles that same sentence
`theme.HEALTH_COLOR["warn"]`, a pairing this codebase already makes and already
tests (`test_ui_usability.py:1101`). The test reads the ANSI code off that rendered
clause and requires the hedge to carry it. A test that had asked `report` which
colour it passed would have passed in both states — this suite's recorded failure
mode, three instances of it in rounds five, forty-seven and forty-eight.

Controls, all green in both states:

* `test_the_other_half_of_the_same_branch_was_already_shared` — the control on the
  harness itself. `render.log_miss_detail` is the `elif` three lines below the
  hedge, single-sourced since round thirty-three, and driving both surfaces at one
  job shows it agreeing. If this one ever reddens the finding is the harness, not
  the hedge.
* `test_the_label_beside_it_is_still_bookkeeping` — the control against
  over-correcting. `log` and the path are chrome; painting the whole line the
  warning hue would say the *path* is suspect rather than the match. Pinned via the
  label plus its reset, so the needle cannot pin the colour it is asserting about.
* `test_the_sweep_still_catches_a_copy_it_used_to_miss` — the non-vacuity control,
  fed the exact pair of spellings that sat in the two front ends rather than
  whatever the package holds today. Under the old byte-for-byte key it reds with
  the two spellings printed side by side, while
  `test_no_sentence_is_written_out_in_both_front_ends` sat **green over the
  duplicate**: that is the blindness, demonstrated rather than asserted.
* `test_the_sweep_ignores_a_column_key_both_specs_look_up` — the other side of it.
  Widening the sweep must not make it fire on the `Column` labels, so lowering
  `_MIN_WORDS` has to break a test rather than a screen.
* `test_both_surfaces_print_the_shared_hedge` — green before the fix too, and worth
  saying why: the two copies **happened to agree** on the words. The defect was the
  two copies, not a disagreement that had already occurred, and this is the guard
  that the next edit to one of them cannot be the disagreement.

### What a user reading old output should know

Nothing that was printed was false. The hedge said the same thing on both surfaces;
`--plain` said it in the hue it uses for a footnote. If you have been reading
post-mortems in `--plain` on a cluster whose scripts do not put the job id in the
log filename, the line telling you the log below might not be this job's was
styled as chrome — it is now styled as the warning it is, and it is one string in
one place.

### Examined and found clean — not changed

* **The overview's count sentence.** `report.py:508` builds
  `"%d job%s in %d workload%s · %s completed"` in one `%`-format; `tui.py:1045-1053`
  builds the same words in four styled `text.append` calls. Not routed through
  `render`, and it cannot be without giving up the per-segment styling the dashboard
  needs. The two agree today on every word, every plural guard and every source
  figure, each file's comment points at the other, and no segment reaches three
  words — so the sweep does not see it either. Left as it is, and named here so the
  next round does not have to re-derive it.
* **`--sizing` versus the workload screen's "next run" banner.** Both draw
  `sizing.recommend`, and they present it differently on purpose: a flag/verdict
  table in `--plain`, a paste-ready `--mem=72G` on the dashboard, which
  `tui.py:1552`'s comment records as a deliberate change. Basis and caution now
  reach both. Not a drift.
* **The job-list qualifiers** (`"%d of them never computed"`, `"%d cancelled"`,
  `"%d unterminated, excluded"`), the excluded-record counts, the footprint note and
  the unclassified note. All single-surface: `render_list` is a bare table by design
  and `--plain` carries these on the overview instead. One stale comment,
  `tui.py:1064`, says "the exclusion count is on the workload screen" — the
  dashboard's workload screen shows `group.excluded` only, not the three-way
  breakdown. Wording, not behaviour; left alone.
* **`tui.py:1815`'s third value branch**, `elif "not recorded" in value: FAINT`.
  `report` has no equivalent because it has no faint. Two words, below the sweep's
  floor, and a per-surface styling choice rather than a sentence.

### Still open

* The note is all but unreachable on `--plain` for a single job id, for round
  forty-eight's reason: `-j` loads only the records asked for and changing that is a
  second `sacct` query. Untouched here. (Round forty-nine's fix means the note *is*
  drawn when the window is given — `slurmpast 53363721_35 --plain --no-logs -S
  now-90days` prints `midway3-0250 failed 32 of 33 placements there (97.0%, 95% CI
  84.7 – 99.5%) against 1.0% …` — so what is open is the bare `slurmpast <id>` case.)
* The local suite collects 2120 against a badge of 1993 because
  `test_parse_cost.py`, `test_portability_round81.py` and
  `test_subprocess_text_mode.py` are untracked (127 tests).
  `test_layout.py::TestTheReadmeAndItsAssetsAgree::test_the_test_badge_matches_the_suite`
  fails locally and passes on CI; committing or deleting those three files closes
  it, flipping the badge would red CI. Unchanged from round fifty-three's note.
* **The overview, the job list and `--sizing` still have no end-to-end routing
  test.** The job screen has one now. What guards the other three is the source
  sweep, which is stronger than it was but is still a sweep — it can prove no
  sentence is written twice, not that what reaches each screen is the shared one.

## Round fifty-five — the direction was read off the data, and the p-value never paid for it

One fix, and it closes the **oldest** item in the Still-open list: round
forty-seven's second, carried unchanged through rounds forty-eight to fifty-four,
each of which recorded it and declined it as "a statistical question, not a
labelling one". 1980 tests before, **1986** here; all four gates clean.

### The item, and why the argument for it had gone stale

Round forty-seven wrote it down with its own reason for leaving it:

> **One-sided p-values chosen after seeing the direction**, pooled into one BH
> family with the opposite direction's. Each row's `p` is effectively a two-sided
> p halved. The docstring records a null simulation putting the realised rate at
> 2.4–2.8% against a 5% target, so the slack absorbs it; noted because the
> argument for it is empirical rather than structural, and nothing re-measures it.

That is an honest deferral and it names its own weak point. "Nothing re-measures
it" turned out to be the whole of the defect, because **the simulation it leans on
measured half the family.** `nodes.py:513` picks the direction from the row's own
rate:

```python
            direction = "worse" if rate > comparison else "better"
```

and the docstring's 2.7% / 2.8% / 2.4% came from `tests/test_nodes.py`'s
`_null_tables`, which counted `suggest_exclude(...)` — the `worse` rows only. A
`better` verdict is a claim off the same table, corrected in the same `_bh_reject`
pass, printed in the same column and read by the same person. Counting one half and
quoting the number against `FDR_ALPHA` compares a half-family rate to a
whole-family promise, and the missing half is the same size as the one that was
counted. So the slack that "absorbs it" was measurement error.

### 1. What it costs, on a null

Re-measured with `_null_tables`' own construction — every node sharing one true
rate, jobs built directly, `workload="w"` — but counting a table as flagged when it
reaches **any** verdict rather than only when it offers one to `--exclude`. 4,000
tables a cell:

```
per node   rate    nodes    tail in the won direction    priced for the direction
30         0.20    10        4.8%                         2.5%
30         0.20    20        4.5%                         2.4%
30         0.20    40        4.7%                         1.2%
30         0.35    20        5.5%                         2.7%
50         0.35    20        6.5%                         3.2%
100        0.35    20        7.8%                         3.7%
100        0.50    20        8.0%                         3.8%
200        0.50    20        8.2%                         4.4%
```

The `worse`-only column reproduced the docstring: 3.5% / 2.7% / 2.7% at 10 / 20 /
40 nodes against its 2.7% / 2.8% / 2.4%, so the harness agrees with the one round
forty-seven ran. Whole-family, the same three cells are 4.8% / 4.5% / 4.7% — under
the 5% target, and **that is the only block where it is.** Give a node more
evidence than 30 placements, or a rate nearer 0.5 where Fisher's 2x2 is least
discrete, and it converges on 8.2% — twice the target, which is exactly what a
one-sided test at nominal 5% run in a direction picked from the data is worth.

So the deferral's premise was right about the mechanism ("effectively a two-sided
p halved") and wrong about the consequence: the slack does not absorb it, it hides
it at one particular sample size. FDR_ALPHA's own comment calls the family "the
table", so this is the code drifting from a rule it states about itself.

Priced, the same grid runs 1.2% – 4.4%, inside the promise across all eight cells
and rising toward it rather than collapsing away from it — the sign of a bound that
is being spent rather than over-paid.

The power cost, measured the same way on the docstring's own case (one node at 0.55
against 0.20 elsewhere, 20 nodes, 1,500 tables): 55% / 82% / 98% at 20 / 30 / 50
placements a node, against 65% / 87% / 99% unpriced. The unpriced figures reproduce
the docstring's 63% / 87% / 98%. The loss is 10 points at 20 placements, 5 at 30
and half a point at 50 — concentrated where the evidence is thin, which is where
this module already says it wants to hold back.

### 2. What it changes on real data

The owner's own history, one `Sacct().history(user="youzhi", since="now-90days")`
fetch: 15,025 records parsed, 15,019 usable, 1,258 workload folds. Both surfaces
rendered twice off that **one** fetch rather than by two CLI runs, because the
cluster is live and a first attempt at the diff drifted by a placement mid-capture
(`15027` → `15028`, and `midway3-0168` from 2/38 to 2/39) — noise that has nothing
to do with the fix.

**The workload-controlled views — the default, and what this module is for — are
byte-identical.** No node stops or starts being named, on either metric:

```
=== hang_controlled       IDENTICAL
=== failure_controlled    IDENTICAL
```

That is not luck, and the reason is worth recording because it bounds who ever saw
this: held to one workload, this window tests 34 nodes at a median of 20 placements
and a maximum of 80 (`--metric failure`: 104 rows, median 15, max 65). Not one row
in either reaches 100. That is squarely inside the protected block of the table
above — the fix lands in the regime where the unpriced test was already passing.

`--all-workloads`, the view the CLI's own `--help` calls "(confounded)", is the
other regime: 308 rows, 26 of them past 100 placements and the busiest at 713.
Three verdicts are withdrawn there, and nothing is added:

```
=== --all-workloads --metric hang
-   midway3-0602            13/161     8.1%        4.8 - 13.3% worse
+   midway3-0602            13/161     8.1%        4.8 - 13.3% inconclusive
-   midway3-0386             3/448     0.7%         0.2 - 2.0% better
+   midway3-0386             3/448     0.7%         0.2 - 2.0% inconclusive
-     #SBATCH --exclude=midway3-[0056,0116,0250,0385,0600-0602]
+     #SBATCH --exclude=midway3-[0056,0116,0250,0385,0600-0601]
-   20 intervals clear the baseline on their own - but about one in twenty ...
+   22 intervals clear the baseline on their own - but about one in twenty ...

=== --all-workloads --metric failure
-   midway3-0235             2/183     1.1%         0.3 - 3.9% better
+   midway3-0235             2/183     1.1%         0.3 - 3.9% inconclusive
-   18 intervals clear the baseline on their own - but about one in twenty ...
+   19 intervals clear the baseline on their own - but about one in twenty ...
```

**`midway3-0602` comes off an `--exclude` line a user pastes into a submission
script**, and its p moved 0.000973 → 0.001947 against a BH step it had cleared by a
factor of two. `midway3-0386` (0.000696 → 0.001393) and `midway3-0235` (0.002558 →
0.005116) lose `better`. Those are the changes the owner sees, and they are the
whole of them. The two withdrawn rows in the `hang` view then show up in
`held_back` (20 → 22, and 18 → 19 for `failure`) — round forty-eight's machinery
picking them up unprompted, so a row now reading `inconclusive` beside an interval
clear of the baseline is still explained on the screen rather than looking like a
contradiction.

### The fix

`src/slurmpast/nodes.py:292` — `selected_direction_p_value`, called at
`nodes.py:520` in `node_table`, replacing the raw `node_p_value` on the line under
the `direction = "worse" if rate > comparison else "better"` that creates the debt.
It returns `min(1.0, 2.0 * node_p_value(...))`.

Three choices inside that, each of which could have gone the other way:

* **Doubling, not a two-sided Fisher tail.** Both are defensible and the null sweep
  was what decided it: for the lopsided 2x2 tables this module actually sees — 3 of
  448, 2 of 183 — the two-sided tail is the *smaller* of the two and so the weaker
  guarantee. Doubling is also the entire arithmetic, which is worth something for a
  number that decides what goes on an `--exclude` line.
* **`node_p_value` is left alone.** It stays the plain one-sided tail. It is
  cross-checked against `scipy.stats.fisher_exact` over 5,986 comparisons (round
  thirty-three, max difference 7.7e-13) and against a hand-computed 10/510, and a
  caller that names its direction in advance owes nothing. The charge belongs at
  the one site that picks a direction it did not commit to in advance.
* **The verdict still needs the Wilson interval too.** Unchanged — BH bounds how
  often the table invents a node, the interval keeps the verdict consistent with
  the CI printed beside it, and intersecting with the priced BH cannot add false
  rejections, so the bound survives it.

The module docstring now carries the whole-family sweep, the corrected power
figures, and — because "nothing re-measures it" is how this stayed open for seven
rounds — which regime a real table falls in and therefore which screens move.

### The test, and the control

`tests/test_nodes.py:1495`, `TestTheDirectionIsPricedBecauseTheDataChoseIt`.

Two teeth, both failing before and passing after (verified by reverting only
`nodes.py:520` to `node_p_value` and leaving everything else in place: 2 failed, 4
passed):

* `test_the_row_carries_twice_the_tail_the_data_picked` — 1 failure in 10
  placements beside 0 in 500. The one-sided tail there is exactly 10/510, so the
  row must carry 20/510. Neutered: `0.0196078 != 0.0392157`.
* `test_a_better_verdict_that_only_restated_the_bad_node_is_withdrawn` — one node
  failing 6 of 10 beside two that went 0 for 20. All three rows are one fact: every
  failure in the leave-one-out rate the clean nodes are measured against is the
  first node's, so "these two are better than the fleet" is "that one is worse"
  said twice more. Unpriced, both clean rows cleared BH's loosest step at 0.0373
  and were published as `better`. Neutered: `0.0373662 != 0.0747324`.

Both expectations are hand-computed hypergeometrics written out as arithmetic, not
read back from the function under test — 10/510, and
`(30*29*28*27*26*25)/(50*49*48*47*46*45)` for the single-term tail of 0 marked in a
20-draw from 50 placements holding 6. This suite's recorded failure mode is a test
that pins the buggy value (rounds five, forty-seven, forty-eight found three), and
a test that had asked the code what the tail was would have passed in both states.

Four controls, all passing in both states:

* `test_the_node_the_evidence_is_actually_about_keeps_its_verdict` — the important
  one, and deliberately in the *same table* as the second tooth: `node000` is
  `worse` either way and stays the whole of `suggest_exclude`. The fix withdraws
  the rows that were handing one node's failures back as two other nodes' virtue.
  It does not withdraw the node.
* `test_the_tail_itself_is_untouched_and_still_one_sided` — pins *where* the charge
  lives. Folding the factor of two into `node_p_value` would make every other test
  in the class pass while breaking the scipy cross-check and the hand-computed
  10/510.
* `test_a_certainty_stays_a_certainty` — 19 of 36 hangs against 12 of 218 on
  identical work, the signal this module exists for, is 2.5e-11 and eleven orders
  of magnitude clear of the line; and the `min(1.0, ...)` cap keeps the priced
  value a p-value.
* `test_the_whole_family_and_not_just_the_exclude_line_stays_flat` — closes the
  measurement gap itself. `_null_tables` grew a `verdict` argument; the default is
  the old `suggest_exclude` count, so the three existing null tests are unchanged,
  and `verdict="any"` is what `FDR_ALPHA` is actually a promise about.

### What a user reading old output should know

A `--nodes` table published before this round used a p-value worth about half what
it claimed for every row that reached a verdict. On the workload-controlled screens
that changes nothing at this cluster's sample sizes — verified byte-for-byte above.
On `--all-workloads` it means a table with 25-plus rows past 100 placements was
offering some verdict on roughly 8% of null tables rather than 5%, and three
verdicts in the owner's own 90-day window do not survive the correction, one of
them a node that was on the exclude line.

### Still open

**Round forty-seven's Still-open list is now empty.** Its first item — the note's
denominator called "your N jobs" — was settled by round forty-eight, which moved
the noun to `placements` and wrote the docstring for why; its second is this round.
What remains open is inherited from later rounds:

* The note is all but unreachable on `--plain` for a single job id, for round
  forty-eight's reason: `-j` loads only the records asked for and changing that is
  a second `sacct` query. Untouched here.
* The local suite still collects 2113 against a badge of 1986 because
  `test_parse_cost.py`, `test_portability_round81.py` and
  `test_subprocess_text_mode.py` are untracked (127 tests). `test_layout.py::
  TestTheReadmeAndItsAssetsAgree::test_the_test_badge_matches_the_suite` fails
  locally and passes on CI; committing or deleting those three files closes it,
  flipping the badge would red CI. Unchanged from round fifty-three's note.

## Round fifty-four — the note named one job for a finding pooled across 154

One fix, closing the second of round **forty-eight**'s Still-open items. 1974 tests
before, **1980** here; all four gates clean.

### Round forty-eight could not reproduce it. It reproduces.

That round recorded the symptom and declined:

> **The note labels the stratum with the raw job name, the nodes screen with the
> folded one.** ... Both *match* on the fold, so the counts agree, and no
> misattribution is reachable on this history: all 403 jobs in that fold carry the
> one raw name. Recorded rather than fixed because it could not be reproduced as a
> wrong count, only as two labels.

The fold it looked at was degenerate. Swept across the whole 90-day history
(15,025 usable jobs, 1,258 folds), **92 folds hold more than one raw name**:

```
  fold            distinct raw names   jobs
  exp-n#                     154        157
  caai-p#a                    96        127
  exp-a#-n#                   87         87
  caai-p#b                    64         77
  caai-p#c                    36         46
```

`cli._node_note` and the dashboard both build `Workload(job.name, job.user)` — one
job's RAW name — while `Workload.matches` normalises before comparing, so
`node_table` pools the whole fold. Measured directly: for a job named `exp-n89`,
`matches` selected **157 jobs spanning 154 distinct names**, and the sentence
labelled that finding "for exp-n89". The count was never wrong. The attribution
was, and a reader would fairly take the finding to be about their `exp-n89` run.

### The rule was already written down

`patterns.fold_erased_the_name` describes itself as "only a *display* rule ...
callers use this to decide whether the key is fit to be read aloud", and
`dominant_workload` applies it — which is why the nodes screen says "only exp-n#
counted". The note applied no display rule at all. `_stratum_label` now does, in
`note_for_allocation` and `note_for_node`, so both front ends get it from the one
place they already share.

Label only: the `workload` handed to `node_table` is untouched, and a control runs
the table with the raw name and with the fold and asserts identical `trials`,
`hits`, rows and verdicts — the premise `dominant_workload` states for its own
substitution, checked rather than trusted.

### What I got wrong first, and the test that caught it

The first version folded unconditionally, and broke two of `test_nodes.py`'s
assertions by turning `caai-p10b_scan` into `caai-p#b_scan`. Those tests were
right to object: that fold pools a single name, so folding traded a true, specific
label for a true, vaguer one — a pattern the reader never typed. **1,166 of the
1,258 folds are that shape**, so it is the common case, not the exception. The
label now folds only where the stratum genuinely spans more than one name, and a
control pins the single-name-with-digits case that exposed it.

The all-digit fallback is unchanged and also pinned: `20260821` folds to `#`,
which names nothing, so the raw name stays — the same fallback `dominant_workload`
reaches for with `newest_name`.

### Still open

* Round forty-eight's third item is untouched: **one-sided p-values chosen after
  seeing the direction**, pooled into one BH family with the opposite direction's.
  That is a statistical question, not a labelling one.
* The note remains all but unreachable on `--plain` for a single job id, for the
  reason round forty-eight gave: `-j` loads only the records asked for, and
  changing that is a second `sacct` query.

## Round fifty-three — one interval, three spellings, and the third option round forty-eight missed

One fix, and it closes the oldest item in the Still-open list -- round **forty-eight**'s,
not round fifty's. 1969 tests before, **1974** here; all four gates clean.

### The item, and why it sat open

Round forty-eight recorded it exactly:

> **The interval in the note is hyphenated where the table's is an en dash.**
> `nodes.py:728` writes `95% CI 84.7-99.5%` by hand while `render.ci_range` — which
> exists *because* "a hyphen and an en dash stood in the same cell depending on which
> one you were looking at" — renders the same two numbers as `84.7 – 99.5%`.

It then declined, and the reasoning is worth quoting because it is where the round went
wrong: *"the choices are to duplicate the format (re-creating exactly the drift `ci_range`
prevents) or to move the sentence out, which is the four-file change described above."*

Both options are bad, and the framing is a false binary. There is a third: **put the rule
where both callers can reach it.** `nodes` may not import `render` -- that is the
architectural rule, and it is why the note had its own spelling -- but `duration` imports
nothing outside the standard library, `render` **already** imports from it, and `nodes` may
import it too. So `duration.format_rate_range` now owns the format, `render.ci_range`
delegates to it, and the note calls it. One home, two callers, no architecture violation,
and no four-file change.

### Rendered, on both surfaces and in both modes

```
                 normal                          --ascii
  note    95% CI 84.7 – 99.5%             95% CI 84.7 - 99.5%
  table          24.6 – 57.7%                    24.6 - 57.7%
```

The en dash is safe in the note for the same reason it is safe in the table:
`render.ascii_fold` maps it to a hyphen, and `report._fold` applies that **once per view
over the finished text** -- "the flag has to reach the sentences as well as the glyphs",
as its own docstring puts it. Verified by rendering job 53363721_35 both ways rather than
by reading the fold path.

Three existing tests pinned the old hyphen incidentally -- round forty-seven's
`test_only_the_noun_moved` control, `test_the_denominator_is_not_presented_as_the_readers_job_count`,
and round fifty-one's `test_control_b_every_figure_the_sentence_already_carried_is_unchanged`.
Each one's subject is a different claim (no figure moved, the denominator's noun, the
figures unchanged) and none was about the separator, so all three keep their subject with
the new spelling. A control in the new file asserts every figure is still present, read off
`node_table` rather than off the sentence.

One control is architectural rather than behavioural: it parses `duration.py` and asserts
it imports nothing outside the standard library. That property is the entire reason this
fix is legal, and if `duration` ever grows a `rich` import the fix silently becomes a
violation -- so it is pinned rather than trusted.

### Note on the README badge

The badge is **1974**, the count of the tree that ships. The working tree here collects
2101 because three test files from earlier rounds (`test_parse_cost.py`,
`test_portability_round81.py`, `test_subprocess_text_mode.py`) are untracked, so
`test_the_test_badge_matches_the_suite` fails locally and passes on CI. That is the correct
way round -- the README is published with the package -- but it means a local full-suite run
shows one failure that CI will not. Committing or deleting those three files is what closes
the gap; flipping the badge to 2101 would red CI instead.

### Still open

* The remaining round forty-eight items are unchanged: the stratum label (raw job name in
  the note, folded name on the nodes screen) and the one-sided p-values pooled into one BH
  family. Neither is cosmetic and neither is touched here.

## Round fifty-two — `format_duration` named a boundary in the unit below it

One fix, found by comparing this tool's formatters against the four sibling
packages' rather than by reading this one on its own. 2091 tests before, **2096**
here; all four gates clean.

### The rule this module states about itself

`format_bytes` says the unit is "chosen for the value as PRINTED, not as stored",
and keeps `_ROUNDS_UP_AT` to enforce it -- added because comparing the raw value
made anything under 1 GiB print "1024.0 MiB" over 13,426 distinct byte values in a
90-day window. `format_duration`, twenty lines above it in the same file, compared
the raw value:

```
  59.95s  ->  "60.0s"      the boundary, spelled in the unit below it
  59.99s  ->  "60.0s"
  0.999s  ->  "1.00s"      two decimals, out of the tier reserved for
                           values that are not yet a second
```

Reachable through any elapsed or CPU figure: a step that ran 59.96 seconds read
"60.0s" where `--time=` and every other duration in the tool would say
`00:01:00`. Both tiers now test the rounded value, so 59.95 promotes to the clock
and 0.999 falls to the tenths tier as "1.0s".

The sub-second tier keeps its two decimals, which the docstring is explicit about
and a control now pins: a hung job's evidence is "0.52s of CPU", and `00:00:00`
would erase the one number the tool exists to surface. 0.52, 0.01, 0.994 and 0
are unchanged, as are 59.9, 59.94, 30, and every clock-shaped output.

### How it was found, and what else the comparison turned up

The five packages format the same quantities, so they were run side by side on
identical inputs. Byte formatting agreed everywhere except the `B` tier, where
`slurmwatch` printed "512.0 B" and "0.0 B" against this module's bare "512 B" --
fixed in that package, citing the bound here that "leaves '1000 B' and '1023 B'
exactly". Duration formatting is deliberately three different shapes (`nodetop`
prints a Slurm clock, `rapidu` a humanised "1h 30m", this one a Slurm clock with a
seconds tier below a minute), and comparing them is what exposed the boundary
above.

### Observed, not fixed

* **`test_portability_round81.py::TestASignalledDashboardRestoresTheTerminal::test_a_clean_quit_is_still_zero`
  is flaky.** It failed during this round's full run, and the failure is not
  this round's: reverting `duration.py` to its previous contents reproduces it
  identically (1 failed / 4 passed either way), and `format_duration` appears
  zero times in that file. Three consecutive runs of the class alone failed 1,
  then 2, then 3 of its five tests with no leaked processes, ptys or fds, which
  points at a timing budget shared across the class rather than at a leak.
  Recorded so a later round does not read it as a regression.

## Round fifty-one — the comparison rate finally says how big it is

One fix, and it is the item round fifty left in its Still-open, in its own words:
**"`_note_from_row` says 'against N% on every other node' and never says how many
placements 'every other node' is."** 2085 tests before, **2091** here; all four
gates clean.

### The sentence was careful about one denominator and silent about the other

Round forty-seven settled how the node's own count is presented -- "failed 32 of
33 placements there", with a whole docstring on why it is `placements` and not
"your 33 jobs". The rate it is compared against got no such treatment:

```
midway3-0432 failed 33 of 344 placements there (9.6%, 95% CI 6.9-13.2%) against 5.3% on every other node.
```

On this cluster's real 90-day history "every other node" is 13,497 placements and
nothing is wrong. Round fifty measured the reachable case: `node_table` applies no
`MIN_HISTORY` -- that floor lives in `note_for_allocation` -- so `--nodes` on a
short window reaches the table directly, where the sentence reads

```
nodeA failed 10 of 10 placements there (100.0%, 95% CI 72.2-100.0%) against 0.0% on every other node.
```

with an every-other-node of **two placements**.

### The bar is the node's own sample size, and it is derived rather than picked

Disclosed when `other_trials < row["trials"]`: when the thing being compared
against rests on fewer placements than the node being accused, the reader is
entitled to know which half of the sentence is thin. At or above it, nothing is
printed.

```
  real history, 90d   other_trials 13,497 vs trials 344   -> silent
  the thin case       other_trials      2 vs trials  10   -> "against 0.0% over 2 placements on every other node"
  the boundary        other_trials     10 vs trials  10   -> silent (below, not at)
```

Two reasons for a bar rather than always printing it. It costs 25 characters of a
one-line job-screen note to tell almost no reader anything -- 13,497 against 344
is not a number anyone needs. And round forty-seven's control
`test_only_the_noun_moved` asserts that its wording change moved no figure and
altered nothing else; an unconditional disclosure broke that control and three
other tests. With the bar the common case is byte-identical and all four pass
untouched, which is the right outcome: a previous round's control should not have
to be rewritten to accommodate a later round.

`over N placements` is `render.nodes_baseline`'s phrasing for the pooled value of
this very field ("baseline 3.4% over 2675 placements"), and that line owns the
noun -- so the words are borrowed rather than invented. The population is threaded
from the table at both call sites (`note_for_allocation`, `note_for_node`), so
both front ends get it from the one builder they already share; `other_trials=None`
keeps the old wording for a caller holding a row without its table.

Withdrawn from this round: nothing. Round fifty's withdrawal of the `other_trials`
floor stands, and this is the narrower change it pointed at.

### Still open

* Nothing new. Round fifty's judgement that a thin comparison arm is already
  priced by the p-value is unchanged; what was missing was disclosure, and the
  reader now has it in the one case where it could matter.

## Round fifty — the `other_trials` floor, withdrawn because the p-value already does the job

No defect fixed. One candidate implemented, measured, and **withdrawn** — the item
round forty-nine left in its Still-open, in its own words: **"`node_table` has no
minimum on `other_trials`"**, with the note that the smallest population earning a
`worse` verdict is 12 records. That is true, and it is still true here. What this
round adds is the measurement that says a count floor is the wrong answer to it.
2085 tests before, **2085** here; all four gates clean.

### What was measured

The reachability sweep round forty-nine asked for, against this cluster's real
accounting database — 15,025 rows over 90 days, 15,019 usable parent jobs — over
both metrics, both the dominant workload and `--all-workloads`, at 7/30/90 days.
For every published verdict, the size of the population it was drawn against:

```
  window  metric   workload   verdicts  min other_trials
  30d     failure  dominant          1             2,664
  30d     failure  all              20            12,076
  30d     hang     dominant          2               931
  30d     hang     all               5            12,939
  90d     failure  dominant          1             2,664
  90d     failure  all              20            13,497
  90d     hang     dominant          2               931
  90d     hang     all               8            14,581
```

**No published verdict on a real history comes within two orders of magnitude of
any floor worth setting.** The smallest is 931 placements. The counting above was
replicated independently of `node_table` and cross-checked against the `trials`
and `hits` it publishes; the two agreed in all eight configurations.

The hole is nonetheless reachable, and round forty-nine was right that
`MIN_HISTORY` is what stands in front of it: that floor lives in
`note_for_allocation` (`nodes.py:705`) and **not** in `node_table`, so `--nodes`
on a short window reaches the table directly. Built synthetically, both
directions publish a verdict off a two-placement comparison:

```
  10 of 10 FAILED on nodeA, 2 COMPLETED on nodeB   -> nodeA "worse"   (comparison 0.0%)
  10 of 10 COMPLETED on nodeA, 2 FAILED on nodeB   -> nodeA "better"  (comparison 100%)
```

### Why the floor was withdrawn

A floor of `MIN_SAMPLES` on `other_trials` — the only value with a derivation,
by symmetry with the arm it already floors — withholds a verdict this repo's own
demo exists to show. `slurmpast --demo --nodes` on the dominant workload has 20
placements in total, so `midway3-0385` at 12 leaves `other_trials = 8`, and its
comparison is 2 of 8 rather than a degenerate 0 of 2. Four tests pin that the
demo names a bad node (`test_audit.py`, `test_cli.py`, `test_tui.py`), and they
are right to: the finding is real.

The p-values are what settle it, because they already price the size of the
comparison arm:

```
  12 of 12 vs 2 of 8    p = 0.000722    the demo's finding, which a floor of 10 suppresses
  10 of 10 vs 0 of 2    p = 0.015152    the case the floor was meant to block
  10 of 10 vs 0 of 10   p = 0.000005    the same node with an adequate comparison
```

A thin comparison arm already yields a p-value twenty times weaker than the
demo's genuine finding. So a hard count is the wrong instrument: it suppresses
p = 0.0007 while the thing actually worth worrying about is p = 0.015 surviving
Benjamini-Hochberg on a table with few rows. That is a question about the size of
the *family*, not about a minimum on the population — and `_bh_reject` is where
it would belong if it is ever worth acting on.

Recorded so the next round does not re-litigate it: the floor was written, the
guard sat in the promotion loop beside the interval and BH conditions, and it was
removed after the demo measurement. `MIN_HISTORY` stays exactly where round
forty-nine put it, and stays the reason the reachable damage is bounded.

### Still open

* **The note's wording, not its statistics.** `_note_from_row` says "against
  N% on every other node" and never says how many placements "every other node"
  is. On a real history that is 13,000 and the omission costs nothing; on the
  synthetic case above it is two, and the sentence is the part that over-claims
  rather than the verdict. Disclosing the comparison population is a wording fix
  with no effect on any verdict, which makes it a smaller and better-targeted
  change than the floor this round withdrew.

## Round forty-nine — one surface said the node was fine, the other said it ate 32 of 33 runs

One defect, fixed, plus the structural cause of it. This is the second of the two
items round forty-eight recorded, in its own words: **"the note is all but
unreachable on `--plain`"** -- deferred there as "a behaviour change to `-j`, not a
wording fix". That change is made here. 2079 tests before, **2085** here; all four
gates clean.

Reproduced against this cluster's real accounting database, on **both** front ends
at the same window, because whether the two agreed was the whole question:
50,604 `sacct` rows over 90 days, 13,075 over 30, 15,040 usable parent jobs. The
dashboard was driven headlessly through Textual's `run_test` and its `JobScreen`
pushed directly at the id under test, so what is quoted below is the compositor's
output rather than a reconstruction of it.

### 1. `slurmpast <one id> --plain` is silent about a node that failed 32 of 33 placements there

`src/slurmpast/cli.py:476` (`_node_note`) read `history`, and on the explicit-id
branch `_load` (`cli.py:359`) returns only the records asked for. So the note was
computed from a history of **one**, where no node can reach `nodes.MIN_SAMPLES`
and the answer is always `""`. The dashboard holds the window whichever screen is
open, so it drew the sentence from the same function, for the same job:

```
$ slurmpast 53363721_35 --plain --no-logs -S now-30days     # BEFORE
  findings

  [WARN] Exited 9, but no log was found to explain it
        An exit status does not name a cause: exit 9 is indistinguishable from a CUDA OOM, a killed
        worker or a bad argument without the stderr text.
        → Pass --log-dir, or set a predictable --error= path.
```

```
dashboard JobScreen(53363721_35), 13,075 rows over the same 30 days:  # BEFORE
   WARN  Exited 9, but no log was found to explain it
         An exit status does not name a cause: exit 9 is indistinguishable from a CUDA OOM, a
         killed worker or a bad argument without the stderr text.
         → Pass --log-dir, or set a predictable --error= path.

   INFO  Node has a history with your jobs
         midway3-0250 failed 32 of 33 placements there (97.0%, 95% CI 84.7-99.5%) against 1.0% on
         every other node for caai-p10b_scan.
         → Consider --exclude if the pattern holds.
```

Same `note_for_allocation`, byte-identical wording, different `jobs` argument.
Round forty-eight verified the *string* cannot drift and that is still true; what
drifted is whether the finding exists at all, which is the one door `render.py`
cannot watch. The reader of the pipeable surface -- the one a script or a
colleague gets -- was told nothing about the machine that had killed 32 of their
33 runs of that workload. It took all 403 ids on the command line to make
`--plain` say it, which is not a thing anyone types.

**Why the population and not the floor.** The obvious reading is that
`len(history) > 20` was too strict, and it is not the defect: measured, with that
gate deleted and the id branch left alone, a one-record history still yields
`''`, because `node_table` drops every node under `MIN_SAMPLES` and one placement
is one. The population was the bug; the floor sat downstream of it.

**What `-j` loads now** (`cli.py:488`, `_node_history`). A node's reliability is a
property of the **window**, not of the job asked about, so the note is computed
from the window on every branch -- which is what every branch except `-j` already
did. The job's own record still comes from `sacct -j`, so `-j` keeps ignoring the
window for the post-mortem itself and an id older than `-S` still reports; only
the comparison population comes from the window, and it comes through `_load`, so
`-p`, `-u`, `--all-users` and `--failed` narrow it exactly as they narrow the
dashboard's. A second, differently-filtered population would just have been new
drift.

```
$ slurmpast 53363721_35 --plain --no-logs -S now-30days     # AFTER
  [WARN] Exited 9, but no log was found to explain it
        ...
        → Pass --log-dir, or set a predictable --error= path.

  [INFO] Node has a history with your jobs
        midway3-0250 failed 32 of 33 placements there (97.0%, 95% CI 84.7-99.5%) against 1.0% on
        every other node for caai-p10b_scan.
        → Consider --exclude if the pattern holds.
```

The agreement is two-sided, which is the part worth checking rather than
assuming. At the **default** `now-7days` window this job is 19 days old and the
window holds no evidence about `midway3-0250` for that workload -- and now *both*
surfaces say nothing, where before one said nothing for the right reason and the
other said nothing for the wrong one:

```
now-7days   (40 rows):     --plain: no node finding      dashboard: no node finding
now-30days  (13,075 rows): --plain: midway3-0250 ...     dashboard: midway3-0250 ...   (same sentence)
```

**The cost, measured rather than assumed.** `-j` now runs a second `sacct` query.
On the default `now-7days` window that is 0.26 s beside the 0.20 s the id query
already cost -- `slurmpast <id> --plain --no-logs` went from 0.33 s to 1.32 s wall
clock. On `-S now-30days` it is 9.3 s for 13,075 rows, and 11.0 s for the 15,046
of `now-90days`: the same query every other mode of the tool already runs for that
window, paid by a caller who asked for that window. `History()` over 13,075
records is 0.35 s and the note itself 0.02 s, so the query is the whole of it.
Two things keep it off the paths that cannot use it: nothing is queried unless
some target job actually has an allocation to say something about, and an empty
window or a `-p` this site has never heard of leaves the note `""` rather than
turning a found post-mortem into an error.

Nothing else moved. `history` is untouched, so the post-mortem, `--json`'s
`summary`/`findings_jobs` and the exit code still come from the `-j` query alone
-- pinned, because folding the window into `history` instead would have printed
80 post-mortems for a one-id question.

### 2. The rule that decides whether the finding exists was written twice, once per front end

`cli.py:477` had `len(history) <= 20` and `tui.py:1708` had `len(history) > 20`:
the same bare literal in the two surfaces, with no single place to read it out of.
That is the shape of defect 1 -- the literals agreed and the arguments did not --
and it is exactly what `render.py` exists to prevent, except that `render` cannot
hold this one, since the analysis modules may not import it. It is now
`nodes.MIN_HISTORY` (`nodes.py:59`), applied inside `note_for_allocation`
(`nodes.py:705`), so both front ends inherit one rule.

**Why the floor exists, since `MIN_SAMPLES` did not make it redundant.** This was
worth working out rather than deleting on the grounds that the statistics already
guard the claim. `node_table` floors the placements on the node being *judged*
(`MIN_SAMPLES = 10`) and **nothing floors the population it is judged against**:
there is no minimum on `other_trials`. Measured, the smallest population that
earns a `worse` verdict is **12 records** -- 10 failures on one node beside 2 clean
runs on another clears `MIN_SAMPLES`, the Benjamini-Hochberg step-up and the
Wilson interval, and produces

```
midway3-0607 failed 10 of 10 placements there (100.0%, 95% CI 72.2-100.0%) against
0.0% on every other node for node-evaluation.
```

-- an "every other node" of two placements. `MIN_HISTORY` is the only thing
standing in front of that sentence, so it is kept at its old value and the move
is behaviour-neutral: `> MIN_HISTORY`, not `>=`, because 20 records is what both
front ends refused and 21 is what they drew. The one quantity that changed is
which records are counted -- `usable(jobs)`, the records `node_table` can actually
use, where `cli` counted `len(history)`, every parsed row including the ones it
then discards. On the history this was measured against that is 15,040 against
15,046, so no reader's note changes.

### Tests

Six, in `tests/test_audit.py` beside the other cross-surface checks, each with a
control that passes in **both** states -- this suite's recorded failure mode is a
test that pins the buggy value, and rounds five and forty-seven found three.

`TestWhetherTheNodeNoteExistsAtAll` builds a fleet of 40 clean placements on
`midway3-0600` and 30 of 40 failing on `midway3-0607`, behind a fake Slurm where
**`-j <id>` answers with that row and nothing else** -- which is what real `sacct`
does, and without which the defect is invisible: a runner answering every query
with the same text cannot show it. Every figure asserted is read off that
construction by hand (30 of 40 is 75.0%; 0 of 40 elsewhere is 0.0%) and none off
the implementation.

* *Teeth* -- `--plain` for one id carries the same four facts the dashboard's
  `JobScreen` carries for it. Fails with the widening removed and the rest of the
  fix left in place; the assertion that fails is on `--plain`, while the
  dashboard's half of it still passes.
* *Control* -- the post-mortem is still only the job that was asked about
  (`● TIME` exactly once, and no fleet id in the body). Passes before and after,
  and fails for a fix that widened `history` rather than the note's population.
* *Control* -- a job on the **clean** node is accused on neither surface. Passes
  before (where `--plain` was silent about every node) and after (where it is
  silent about this one because the statistics say so), so a fix that printed the
  note unconditionally fails here.

`TestOneFloorForBothSurfaces` covers the floor's new home:

* *Teeth* -- at exactly `MIN_HISTORY` records, and again in the 12-record case,
  `node_table` reaches `verdict == "worse"` and `note_for_allocation` still returns
  `""`. Fails with the floor line deleted.
* *Pin* -- one more record is where it starts speaking, so the threshold is
  located rather than merely present.
* *Control* -- a population well above the floor is unchanged. Passes before and
  after, so the move cannot have narrowed what a real history says.

### What changes for a user

`slurmpast <jobid>` and `slurmpast <jobid> --json` now report a bad node the way
the dashboard always has, for the window `-S` names, and the two surfaces agree in
both directions. The cost is one extra `sacct` query on that path: ~1.0 s at the
default window, and the window's own query time when a wide `-S` is asked for.
No `--json` key was added or removed -- 103 values per job, unchanged. `--nodes`,
`--overview`, `--patterns` and `--sizing` are untouched.

### Still open

**`node_table` has no minimum on the comparison population.** `MIN_HISTORY` is a
floor on the whole loaded history, which is a proxy for the thing that actually
wants one: `other_trials`, the placements the judged node is compared against. The
principled fix is a minimum there, beside `MIN_SAMPLES`, which would let the
history floor go entirely. Left alone deliberately -- it changes `--nodes`'
published verdicts and not just this note, so it is a `node_table` decision with
its own numbers to measure, not a rider on a drift fix.

## Round forty-eight — a censored count called "your N jobs"

One defect, fixed. It is the first of the two items round forty-seven recorded as
**Still open**, deferred there because the honest phrasing "has to be settled on
both surfaces at once (`render.nodes_baseline` says 'placements', this says
'jobs') and that is a `render.py` decision, not a `nodes.py` one". That decision
is made here. 2074 tests before, **2079** here; all four gates clean.

Reproduced against the same real history round forty-seven used — 50,591 `sacct`
rows over 90 days, 15,040 usable parent jobs — and drawn on **both** front ends,
the dashboard headlessly through `run_test`, because whether the two agreed was
the open question rather than an assumption.

### 1. "failed 32 of your 33 jobs there", where `sacct` shows 36 rows

`src/slurmpast/nodes.py:728` (`_note_from_row`, defined at 691). Reached from
`cli.py:482` on `--plain`, `tui.py:1715` on the dashboard, and carried in
`--json` as the `node-history` finding's `detail`.

**What the denominator actually is.** It is `row["trials"]`, and since round
forty-seven that is the count of placements `_informative` admits: not cancelled,
and — for the failure metric — not `OUT_OF_MEMORY`. So it counts *runs on this
node whose outcome could have been the node's doing*, which is not the same set
as *runs the reader submitted there*. On round forty-seven's own worked examples
the gap is large:

```
$ awk -F'|' '$1!~/\./ && $5=="midway3-0250" && $2=="caai-p10b_scan" \
    {s=$3; sub(/ by .*/,"",s); print s}' sacct90.txt | sort | uniq -c
      3 CANCELLED
      1 COMPLETED
     32 FAILED
$ awk -F'|' '$1!~/\./ && $5=="midway3-0187" && $2=="caai-p10b_scan" \
    {s=$3; sub(/ by .*/,"",s); print s}' sacct90.txt | sort | uniq -c
      7 COMPLETED
     14 OUT_OF_MEMORY
```

36 rows on `midway3-0250` behind a printed 33, and 21 behind a printed 7 on
`midway3-0187`. Across the whole workload, 403 raw placements and 242 informative
ones.

The censoring itself is right and is not touched: Slurm records `OUT_OF_MEMORY`
when the job's cgroup passed the memory *the job asked for*, and every node that
honours `--mem` enforces the same number, so the outcome says nothing about the
machine. But **"your 33 jobs there" is a claim about the reader's own submissions,
and it is false by three** — in the one sentence in this tool that addresses them
in the second person, and the one most likely to be checked against `sacct`. A
reader who checks it finds 36 and concludes the tool cannot count. The possessive
is what turns a count into that claim, so it went with the noun.

**What the other surfaces already call the same field.** `render.nodes_baseline`
prints the *pooled* value of it — `baseline 3.4% over 2675 placements` is
`table["trials"]` where the note prints `row["trials"]`. `render.nodes_empty_reason`
says "No node reached the 10 **placements** a comparison needs". This module's own
docstrings say placements throughout, and so does `demo.py:210` ("12 placements
there, all 12 hung"). The table's `N` column and `--json`'s `trials`/`bad` are
keys rather than prose and are deliberately outside the question. So the word
already existed on both prose sentences `render` owns, and `_note_from_row` was
the only place that used a different one — and the only one that made it
possessive.

**The noun picked: `placements`, and the possessive dropped.** Nothing new is
coined, which was the brief: a fourth word for one field would be the same defect
one layer on. "Placements" carries no claim about who submitted what, which is
exactly the property the sentence needed, and it is already the word beside the
number two screens away. `render.nodes_baseline`'s docstring now records that it
owns the noun for `trials` and that every prose sentence about that field takes
it, so the next round has somewhere to look rather than a second free choice.

**Why the fix is not literally *inside* `render.py`.** `render` imports this
module (`from .nodes import MIN_SAMPLES`) and imports `rich`, and the analysis
modules may not import a third-party package — so `nodes` cannot call `render`,
and moving the sentence there would mean `note_for_allocation` returning a row
for `cli`, `tui` and `diagnose(node_note=…)` to assemble: a four-file signature
change, not a wording fix. It is not needed for the property `render` exists to
guarantee, either. The sentence is *already* single-source — one function, both
front ends — and that was verified rather than assumed, below. What `render`
owned here was the vocabulary, and that is what it now states.

**Both surfaces, before.** `--plain`, and the dashboard driven headlessly over
the same 90-day history:

```
$ slurmpast <the 403 caai-p10b_scan ids> --plain --no-logs
  [INFO] Node has a history with your jobs
        midway3-0250 failed 32 of your 33 jobs there (97.0%, 95% CI 84.7-99.5%) against 1.0% on
        every other node for caai-p10b_scan.
        → Consider --exclude if the pattern holds.

# JobScreen(job 53363721_35), textual run_test, 100x50
  INFO  Node has a history with your jobs
        midway3-0250 failed 32 of your 33 jobs there (97.0%, 95% CI 84.7-99.5%) against 1.0% on
        every other node for caai-p10b_scan.
        → Consider --exclude if the pattern holds.
```

**And after:**

```
  [INFO] Node has a history with your jobs
        midway3-0250 failed 32 of 33 placements there (97.0%, 95% CI 84.7-99.5%) against 1.0% on
        every other node for caai-p10b_scan.
        → Consider --exclude if the pattern holds.

  INFO  Node has a history with your jobs
        midway3-0250 failed 32 of 33 placements there (97.0%, 95% CI 84.7-99.5%) against 1.0% on
        every other node for caai-p10b_scan.
        → Consider --exclude if the pattern holds.
```

**The two surfaces agreed, before and after — so there is no second finding
there.** That is the answer to the question round forty-seven left, and it is a
fact about where the sentence lives rather than a lucky coincidence: both front
ends call the same `nodes.note_for_allocation`, so the string is byte-identical by
construction. The `--nodes` screen is likewise unchanged and identical on both,
still `baseline 3.4% over 2675 placements`, since only a docstring moved in
`render`.

### Tests

Five added, in one class at the end of `tests/test_nodes.py:1360`. The fixture is
the real per-node shape of `caai-p10b_scan`: the seven nodes that reach
`MIN_SAMPLES` spelled exactly, in the states `sacct` writes here, plus the 27
sub-threshold nodes as their informative counts really are distributed (9×1, 6×2,
4×3, 4×4, 2×6, 2×7 = 75). It reproduces the real table row for row —
`trials=242, hits=34, tested_nodes=6, skipped_nodes=28`, `midway3-0250` at
32/33 — and the tail is load-bearing rather than padding: without it the
leave-one-out comparison is 2/108 and the sentence reads 1.9% instead of the real
2/209 → 1.0%. Round forty-four's lesson about fixtures.

The two that fail before and pass after:

* the sentence, asserted whole, plus its denominator derived from the fixture's
  own rows — `raw = 36` and `censored = 3` are counted off the job list, and the
  assertion is `"failed 32 of %d placements there" % (raw - censored)`. Not off
  `row["trials"]`: a count recomputed from the same reference the implementation
  used is the failure mode round five named and round forty-seven found a third
  instance of, and it would have held whichever noun was printed.
* the vocabulary agreement — `"over 242 placements" in nodes_baseline(table)` and
  `"33 placements" in note`, with the literal written by the test rather than
  read out of either module.

The controls, each passing in **both** states:

* **Only the noun moved.** `note.startswith("midway3-0250 failed 32 of ")` and
  `note.endswith("(97.0%, 95% CI 84.7-99.5%) against 1.0% on every other node for
  caai-p10b_scan.")` — every figure in the sentence is the same before and after.
  A wording fix that moved a number would be a different defect, and this is what
  says it did not.
* **The censoring is still in place.** `(bad, trials) == (32, 33)`,
  `(table["trials"], table["hits"]) == (242, 34)`, and `midway3-0187` still gets
  no note at all — 33 is the right number, and the fix is what it is *called*.
* **A node that behaved is still given no sentence.** `midway3-0200`, 0 of 16 on
  the same workload and the same 48-CPU/184320 MB hardware as `midway3-0187`,
  stays unnamed: the `verdict != "worse"` guard above the wording is untouched.

Teeth checked by restoring the old format string and nothing else. Exactly the two
new assertions fail; all three controls pass. **No pre-existing test failed with
the old wording restored**, which is the honest report on coverage: nothing in the
suite pinned this noun in either direction, so it was free to drift.

Two docstrings that quoted the sentence were updated with it —
`tui.py:336` and `tests/test_tui.py:1326`, both of which use the note as their
worked example of the longest prose the dashboard draws.

### Examined and found clean — not changed

* **The comparison the note prints.** `1.0%` is `row["comparison"]`, the
  leave-one-out rate, and the sentence names it as what it is — "on every other
  node". Round forty-seven moved `held_back` off `comparison` precisely because it
  appears nowhere the reader can see; here it is printed in the same breath, so
  the objection does not apply.
* **`_informative` and `dominant_workload`.** Untouched. `--metric hang` still
  counts every placement, and the failure screen still controls on `sixdeg` and
  still offers `#SBATCH --exclude=midway3-0506`.

### Still open

* **The interval in the note is hyphenated where the table's is an en dash.**
  `nodes.py:728` writes `95% CI 84.7-99.5%` by hand while `render.ci_range` — which
  exists *because* "a hyphen and an en dash stood in the same cell depending on
  which one you were looking at" — renders the same two numbers as `84.7 – 99.5%`
  in the node table. One interval, two spellings, in one tool. Not fixed for the
  same reason the sentence did not move: `nodes` cannot import `render`, so the
  choices are to duplicate the format (re-creating exactly the drift `ci_range`
  prevents) or to move the sentence out, which is the four-file change described
  above. It is a cosmetic inconsistency, not a wrong number.
* **The note labels the stratum with the raw job name, the nodes screen with the
  folded one.** The note says "for caai-p10b_scan" (`Workload(job.name, …)`) where
  the nodes screen says "only caai-p#b_scan counted"
  (`dominant_workload`'s normalised label). Both *match* on the fold, so the
  counts agree, and no misattribution is reachable on this history: all 403 jobs
  in that fold carry the one raw name. Recorded rather than fixed because it could
  not be reproduced as a wrong count, only as two labels.
* **The note is all but unreachable on `--plain`.** `cli._node_note` requires
  `len(history) > 20`, and on the job-ids branch `_load` returns only the records
  asked for — so `slurmpast <one id>` has a history of one and prints no note at
  all, while the dashboard computes it from the whole window. It took all 403 ids
  on the command line to make `--plain` draw the sentence above. Same function,
  different `jobs` argument. Not a wording defect, and fixing it means changing
  what `-j` loads (a second `sacct` query), which is a behaviour change rather
  than this round's scope.
* **One-sided p-values chosen after seeing the direction**, pooled into one BH
  family with the opposite direction's — round forty-seven's second open item,
  unchanged and un-remeasured here.

## Round forty-seven — a healthy node offered to `--exclude`, and a count the screen could not show

Two defects, both fixed, both in `nodes` — the module that makes the sharpest
claims about things outside the user's control, and the one nothing since round
thirty-three has been through. Rounds twenty-five, twenty-six and twenty-seven are
the last that changed how a node is judged; the fourteen rounds after them went
elsewhere. 2064 tests before, **2074** here; all four gates clean.

Both were reproduced against real `sacct` over this cluster's own history —
50,604 rows, 15,051 parent rows in a 90-day window — and both against
`scontrol show node` for what the cluster says about the machines being accused.

### 1. `OUT_OF_MEMORY` counted as the node failing, and put a healthy node on the exclude line

`src/slurmpast/nodes.py:318` (`_informative`, defined at 267), read at
`nodes.py:404` in `node_table`, acted on at `nodes.py:599` (`suggest_exclude`).

This is the one output a user pastes into a submission script, and it named a
machine that had done nothing:

```
$ slurmpast --plain --nodes --since now-90days --metric failure
node reliability — failure rate
  controlled for workload: only caai-p#b_scan counted (placement is not random)
  baseline 33.5% over 313 placements; 33 nodes below threshold omitted

  NODE                         N     RATE             95% CI VERDICT
  midway3-0250             32/33    97.0%       84.7 – 99.5% worse
  midway3-0187             14/21    66.7%       45.4 – 82.8% worse
  midway3-0376             17/64    26.6%       17.3 – 38.5% inconclusive
  midway3-0330              9/45    20.0%       10.9 – 33.8% better
  midway3-0308              2/12    16.7%        4.7 – 44.8% inconclusive
  midway3-0386              1/17     5.9%        1.0 – 27.0% better
  midway3-0200              0/16     0.0%        0.0 – 19.4% better

  worse than every other node, after correcting for 7 nodes tested:
    #SBATCH --exclude=midway3-[0187,0250]
```

All 14 of `midway3-0187`'s failures are `OUT_OF_MEMORY`, and so are all 17 of
`midway3-0376`'s and 7 of `midway3-0330`'s. 71 of the 105 flagged placements in
that workload — 68% — are OOM:

```
$ awk -F'|' '$1!~/\./ && $2~/caai-p.*b_scan/ {s=$3; sub(/ by .*/,"",s); print $5, s}' sacct90.txt \
  | sort | uniq -c | grep -E '0187|0200|0250'
      7 midway3-0187     COMPLETED
     14 midway3-0187     OUT_OF_MEMORY
     16 midway3-0200     COMPLETED
      3 midway3-0250     CANCELLED
      1 midway3-0250     COMPLETED
     32 midway3-0250     FAILED
```

`midway3-0187` and `midway3-0200` are the same machine to the scheduler, and
`midway3-0200` went 0 for 16 on the same workload:

```
$ scontrol show node midway3-0187 | grep -oP '(CPUTot=\S+|RealMemory=\S+|Gres=\S+)'
CPUTot=48 Gres=(null) RealMemory=184320
$ scontrol show node midway3-0200 | grep -oP '(CPUTot=\S+|RealMemory=\S+|Gres=\S+)'
CPUTot=48 Gres=(null) RealMemory=184320
```

The OOM is the submission's, not the machine's. Every element of the array asked
for the same 6 GB, and 71 of 142 died on ten different nodes:

```
$ sacct -j 53363721 -X -o JobID,ReqMem,ReqTRES%40,State,NodeList | head -5
       JobID     ReqMem                                  ReqTRES      State        NodeList
53363721_0          6Gn            billing=1,cpu=1,mem=6G,node=1 OUT_OF_ME+    midway3-0195
53363721_1          6Gn            billing=1,cpu=1,mem=6G,node=1 OUT_OF_ME+    midway3-0386
53363721_2          6Gn            billing=1,cpu=1,mem=6G,node=1 OUT_OF_ME+    midway3-0178
```

Slurm records `OUT_OF_MEMORY` when the job's cgroup passed the memory *the job
asked for*. That limit is a property of `--mem` and every node that honours the
request enforces the same number, so the outcome carries no information about
which node ran it. The module's own docstring names this class of confound —
*"most of that is 51 `cot-exp` timeouts, i.e. a code bug, not the node"* — and
offers the workload control as the answer. **The workload control cannot reach
this one**, because one array's elements do not all need the same memory: the
high-index elements of `53363721` need more than 6 GB wherever they land, and
they do not land evenly.

`_informative` already censors cancellations from *both* halves of the rate, with
the argument that leaving an uninformative row in the denominator "is counting an
unknown as a success, and it is the one thing this module does that the rest of it
argues against". OOM was worse than that case: it was in the **numerator**, and it
is not ambiguous — it is known not to be the node's doing. It is now censored the
same way, for the failure metric only.

**Fix:** `not job.cancelled and job.base_state != "OUT_OF_MEMORY"`. `midway3-0187`
drops to 0 of 7 informative placements — below `MIN_SAMPLES`, which is what this
module already says it wants to answer when the informative sample really is that
small — and leaves the table entirely. `midway3-0376` goes 17/64 → 0/47.
The exclude line becomes `#SBATCH --exclude=midway3-0250`, the node whose 32
failures are real `FAILED` rows. **The fix narrows the claim without costing the
signal.**

**What was deliberately not changed:** `TIMEOUT` and `DEADLINE` stay in the
failure rate. A wall-clock kill really can be the machine — a wedged mount, a
stuck GPU — and the hang metric this module was *built* on is exactly that signal
(the founding measurement in the docstring is 19 hangs in 36 on `midway3-0385`).
Removing them would gut the module's own reason for existing. The hang metric also
keeps OOM placements in its denominator, and that is not an inconsistency: a job
that got far enough to be killed for its memory is evidence the node did *not*
hang.

#### 1b. The same fix in `dominant_workload`, because the selection has to match

`src/slurmpast/nodes.py:571`.

`dominant_workload` ranked workloads by raw `_bad` count while `node_table` tests
only the informative placements, so once OOM is censored it could pick a stratum
whose every failure the table then discards — the exact "eight rows of nothing"
its own docstring was written to prevent.

Not hypothetical: **15 workloads in this history have failures that are 100%
`OUT_OF_MEMORY`**, and the condition is reachable in **92 distinct `-S`/`-E`
windows**. The largest case is `rd-r#-recon` — 16 failures in 33 runs, every one
OOM — which over `-S 2026-08-10 -E 2026-08-14` outranks `nemotron-api`'s 12
genuine `FAILED` rows, wins the selection, and arrives at the table with
`tested_nodes=0, hits=0`. Selecting over the same censored view picks
`nemotron-api` and gets a node tested against 12 real failures.

The selection is now made over the placements `node_table` will actually test,
falling back to the whole set when the censoring empties it so a window of nothing
but cancellations still names a workload rather than raising on `max(())`. With no
metric named the choice is still by run count, unchanged.

**What a user sees change on the failure screen:** the 90-day window now controls
on `sixdeg` (2,675 placements, 3.4% baseline, 104 nodes tested) instead of
`caai-p#b_scan` (313 placements, 7 nodes), and finds `midway3-0506` at 7/11 =
63.6% — 7 real `TIMEOUT` rows. A better-powered table on a workload whose failures
the test can actually speak to. The default `--metric hang` screen is untouched.

### 2. `held_back` counted against a rate the screen never prints

`src/slurmpast/nodes.py:490`, read at `src/slurmpast/render.py:810`
(`held_back_note`) and drawn by both front ends.

`held_back_note` says *"N intervals clear **the baseline** on their own"*. The
baseline the screens print is the pooled one from `render.nodes_baseline`.
`held_back` was counted against each row's leave-one-out `comparison` — a number
that appears nowhere the reader can see. So the sentence written to stop the table
contradicting its own CI column could itself send the reader hunting for a row
that is not there.

On the **default** screen of a real 90-day history:

```
$ slurmpast --plain --nodes --since now-90days --metric hang
  controlled for workload: only rd-s#-run counted (placement is not random)
  baseline 8.2% over 987 placements; 49 nodes below threshold omitted
  ...
  midway3-0316              7/32    21.9%       11.0 – 38.8% inconclusive
  ...
  midway3-0039              1/65     1.5%         0.3 – 8.2% inconclusive
  ...
  2 intervals clear the baseline on their own — but about one in twenty does that
  by chance and 34 nodes were tested, so on its own that is not yet evidence.
```

Two claimed, one findable. `midway3-0316` at 11.0–38.8% clears the printed 8.2%.
`midway3-0039` does not: its interval ends at 0.082135 against a printed baseline
of 0.082066 — indistinguishable at one decimal place, and *above* it — but below
its own `comparison` of 0.086770, so it was counted.

The over-count runs in one direction only, and always that one: `baseline` is a
convex combination of a row's own rate and its `comparison`, and a Wilson interval
always contains its own rate, so clearing the baseline implies clearing the
comparison and never the reverse. `held_back` was therefore a superset of what the
reader can verify, never a subset.

**Fix:** count against `baseline`. The line now reads `1 interval clears the
baseline on its own`, matching the one row on screen.

**A test pinned the buggy reference.** `tests/test_nodes.py:410` recomputed the
count off `r["comparison"]` — the same wrong reference the implementation used —
so the assertion held whichever of the two did. This is the third instance of the
failure mode round five named ("a test that pins the buggy value"); it now
recomputes off `table["baseline"]`, which is the number the sentence names.

### Tests

Ten added, in three classes at the end of `tests/test_nodes.py`. Every fixture is
spelled in states `sacct` actually writes here (`OUT_OF_MEMORY`, `FAILED`,
`TIMEOUT`, `COMPLETED`) on real `midway3-NNNN` node names, and each of the three
reproduces the numbers pasted above rather than a convenient shape — round
forty-four's lesson about fixtures.

The controls are deliberate, and each passes in **both** states:

* `midway3-0250` is still `worse` and still the sole `--exclude` suggestion —
  the control that shows fix 1 narrows the claim rather than blunting the table.
* The hang metric still counts all 179 placements of that workload, OOM included.
* `_informative(timed_out, "failure") is True` — the control that keeps fix 1
  from over-reaching into `TIMEOUT`.
* With no metric named, `dominant_workload` still ranks by run count and still
  picks `rd-r#-recon` (76 runs against 42) — so the change is confined to the
  metric path.
* A row that *does* clear the printed baseline (`midway3-0316`, 7/32 over a 7.2%
  baseline) is still counted in `held_back` — the note must not be silenced for
  the row it exists for.

Teeth checked by neutering only the lines each fix added, one at a time, and
confirming the new assertions fail and the controls do not.

### Examined and found clean — not changed

* **Attribution across a multi-node allocation.** `node_table` credits a failure
  to every node in the expansion, and `total_trials` counts one placement per
  node, so numerator and denominator agree. 29 of 15,051 parent rows here are
  multi-node (0.19%), the largest being `beagle3-[0012,0015,0035,0038],midway3-
  [0304-0307,0377-0378,0424-0427]`. `note_for_allocation` returns "" on all 29,
  correctly: each one's own workload is far under `MIN_SAMPLES`.
* **The denominator.** Rows are ranked by *rate*, not by raw failure count, and
  `MIN_SAMPLES = 10` gates entry, so a node used twice is never ranked beside one
  used 400 times. The brief's worry does not apply.
* **The correction family.** `note_for_allocation`'s docstring claims the BH
  correction is applied "over the table, not a per-node slice of it"; it is —
  one `node_table` call per allocation, `_bh_reject` over every row, and the row
  indices still align because `rows.sort` happens after the loop that reads
  `survived`.
* **`node_p_value`'s tails.** Both directions were re-derived by hand: `worse`
  sums pmf over `[bad, high]`, `better` over `[low, bad]`, and both include `bad`.
  The early break is correctly gated on the mode being behind the walk.
* **`_bh_reject`.** Standard step-up, taking the largest satisfying rank, over
  every examined row including the `p = 1.0` ones — which is the right `m`, and is
  what the code says it is doing.

### Still open

* **The note's denominator wording.** `_note_from_row` says "failed %d of your %d
  jobs there", and `%d` is now the *informative* placement count — neither
  cancellations nor OOM. On `midway3-0250` that reads "failed 32 of your 33 jobs
  there" where `sacct` shows 36 rows on that node for the workload. Censoring the
  denominator is right; calling the result "your N jobs" is not quite. Left alone
  rather than reworded mid-round, because the honest phrasing has to be settled on
  both surfaces at once (`render.nodes_baseline` says "placements", this says
  "jobs") and that is a `render.py` decision, not a `nodes.py` one.
* **One-sided p-values chosen after seeing the direction**, pooled into one BH
  family with the opposite direction's. Each row's `p` is effectively a two-sided
  p halved. The docstring records a null simulation putting the realised rate at
  2.4–2.8% against a 5% target, so the slack absorbs it; noted because the
  argument for it is empirical rather than structural, and nothing re-measures it.

## Round forty-six — a site cause asserted from a fact the tool never held

Two defects, both fixed, both in `site` — the module whose whole job is to stop
this tool asserting things about "the cluster" that are only true of one. This is
the item rounds forty-four and forty-five both recorded as **Still open**, and it
is settled here. 2060 tests before, **2064** here; all four gates clean.

**The live reproduction of the primary defect was not obtained, and is not
available on this cluster.** The stated reason both previous rounds deferred it
holds, and was re-confirmed mechanically rather than assumed:

```
$ scontrol show config | grep -i AccountingStorageTRES
AccountingStorageTRES   = cpu,mem,energy,node,billing,fs/disk,vmem,pages,gres/gpu
```

The list is published, so `tracks_gpu_utilization` is False here and never None,
and the broken branch cannot be reached from this scheduler's answer. What was
done instead is what settles it: the defect is a contradiction between the code
and a rule the module states about **itself**, which is true independently of
which clusters can show it; and the second defect below is the shape that makes
the branch reachable from a real `scontrol show config` — which is why the two
belong in one round rather than two.

### 1. `gpu_utilization_note` treated `None` as False

`src/slurmpast/site.py:402` (the note), read at `src/slurmpast/render.py:1492`.

The module docstring, `site.py:17`:

> Every field degrades to None when the scheduler cannot be reached, and every
> caller must treat None as "cannot say" rather than as a default -- the same rule
> the rest of the codebase applies to a missing measurement.

`cpu_total_is_complete` restates it at `site.py:346` — *"None is not False, per
this module's rule -- an unknown gather type does not license the pessimistic
claim"* — and `maxrss_caveat` and `cpu_caveat` are both built as three arms with
`is None` first. `gpu_utilization_note` was two arms on truthiness:

```python
if current.tracks_gpu_utilization:      # None falls through
    return "not recorded for this job"
if not current.known:
    return "not recorded by Slurm"
return "not gathered by this cluster (needs AutoDetect=nvml in gres.conf)"
```

`known` is the wrong guard, and that is the whole defect. It is true of a config
that *was* read but carried no TRES list, so only half the None cases reached the
hedge and the other half bought the diagnosis. Driven with all three inputs, on
the pre-fix code:

```
gres/gpuutil present                 True  -> 'not recorded for this job'
list read, no gpuutil (this cluster) False -> 'not gathered by this cluster (needs AutoDetect=nvml in gres.conf)'
config read, TRES absent -> None     None  -> 'not gathered by this cluster (needs AutoDetect=nvml in gres.conf)'
scontrol unreachable                 None  -> 'not recorded by Slurm'
```

Row three is the bug: `known` is True, the TRES list was never seen, and the
reader is told to go set `AutoDetect=nvml` in `gres.conf` on the strength of it.
Rows two and three are also *indistinguishable in the output*, which is what the
`is None` arm separates. Now three arms keyed on the property rather than on a
similar-looking one, and row three reads `not recorded by Slurm`.

Not a wording change: the old sentence names a file to edit. On a site whose TRES
list simply was not in the answer, `gres.conf` may already say `AutoDetect=nvml`.

### 2. `(null)` was read as a value, and printed as one

`src/slurmpast/site.py:122` (the sentinel), `src/slurmpast/site.py:144` (the read).

Where the value is READ, which is where defect 1's branch becomes reachable from
real output. `scontrol show config` renders an unset string key as the literal
`(null)`, and `_parse_config` had no handling for it. This is not a hypothetical
shape — it is what this cluster's own `scontrol show config` prints, on **59 of
its keys**:

```
$ scontrol show config | grep -oE '= \((null|none)\)' | sort | uniq -c
     59 = (null)
```

`AccountingStorageParameters`, `JobAcctGatherParams`, `AuthInfo`, `DebugFlags`
and `JobDefaults` are among them. Kept as a value the sentinel is **truthy**, so
it skipped every "cannot say" arm in the module and then got printed inside the
sentence. Pre-fix, on that shape:

```
parsed tres            = ('(null)',)
tracks_gpu             = False        # should be None
tracks_gpu_utilization = False        # should be None
rss_from_cgroup        = False        # should be None

maxrss_caveat -> 'MaxRSS sums RSS across the process tree under (null), double-counting shared pages, so treat it as an upper bound'
cpu_caveat    -> "TotalCPU is summed over the step's process tree under (null), so work in processes reparented away from it — ... — is not counted; treat it as a lower bound"
```

Two failures in one: a confident claim from a fact not held, and the sentinel
leaking into user-visible prose. Now normalised to `""` at the read, so no
property has to know, and the module's own None path carries it: `tres == ()`,
`rss_from_cgroup is None`, and `maxrss_caveat` gives the *"depending on this
cluster's JobAcctGatherType"* arm.

**Stated plainly, because it is the limit of the evidence:** the `(null)`
rendering is live-verified from the real command on the real cluster, for keys of
the same type and in the same `Key = value` format. It was **not** observed on
`AccountingStorageTRES` or `JobAcctGatherType` specifically — those are set here.
Which key is unset is a site property; that any of the five this module reads
*can* be is what the fix covers.

### Tests, controls and teeth

Four tests, in the two classes that own the code. The fixtures carry shapes the
real `scontrol show config` produces — the `(null)` sentinel above, the
`Configuration data as of ...` preamble, and for the controls the cluster's own
published TRES list, asserted against `conftest.RECORDED_SITE` so it cannot drift
from the recorded configuration.

The two controls are written against this suite's recurring failure mode — a test
that pins the buggy value. Neither pins an output the fix changed:

* `test_a_tres_list_that_was_read_still_earns_the_site_cause` — a list that *was*
  read and genuinely lacks `gres/gpuutil` still gets the `AutoDetect=nvml`
  diagnosis. That arm is correct, and it is this cluster's real configuration.
  The control is what stops the new hedge from swallowing the other two arms.
* `test_a_key_that_is_set_survives_the_sentinel_check` — set keys parse whole, and
  `JobAcctGatherFrequency = task=30,network=60` still yields 30, i.e. the value
  keeps the `=` inside it. That last one guards the line the fix edited.

Teeth, in three stages, neutering only what this round added and restoring from a
copy rather than from HEAD. Reverting **only** the note fails exactly its own test
and leaves the parsing test green; reverting **only** the sentinel normalisation
fails exactly the parsing test and leaves the note test green; reverting both
fails both. All four controls pass in all four states, so each fix is
independently pinned.

### Numbers a user might be depending on

None changed. No `--json` key was added or removed — still **103** values per job
and 40 per step. The only user-visible change is which of three existing
sentences the GPU utilization row prints, and only for a cluster whose TRES list
`scontrol` did not report; on this cluster every sentence is what it was.

Fully addressed: both defects above, and the item carried forward from rounds
forty-four and forty-five is now closed. Nothing withdrawn. Nothing left open from
this round — with the one honest caveat recorded above, that the primary defect's
live reproduction is not obtainable from a cluster that publishes its TRES list,
and was argued from the module's own stated rule instead.

## Round forty-five — a step killed inside a job that reported success

One defect, fixed. It is the item round forty-four recorded as **Left open** with
"closing it needs a `derived_signal` field on `Job`, so it is a round of its own" —
this is that round. Found and closed against this cluster's accounting database:
50,619 rows over 90 days, 15,060 of them parent rows. 2052 tests before, **2060**
here; all four gates clean.

### 1. `DerivedExitCode` is `code:signal` too, and only the code was read

`src/slurmpast/sacct.py:854` (extraction), `src/slurmpast/render.py:1515`
(the `worst step exit` gate), `src/slurmpast/model.py:200` (the field that was
missing), `src/slurmpast/cli.py:583` (the `--json` payload).

The same defect class as round forty-four's, one field over. `ExitCode` and
`DerivedExitCode` are both `code:signal`, and slurmdbd writes a signal kill with a
**ZERO** code — so `derived_code, _ = _parse_exit(...)` threw away the only half
that carried the news, and the row meant to report it then compared `0` against
`0`:

```python
derived_code, _ = _parse_exit(get(row, "DerivedExitCode"))         # sacct.py:854
...
if job.derived_exit_code not in (None, job.exit_code):             # render.py:1515
    outcome.append(("worst step exit", str(job.derived_exit_code), None))
```

Measured, not argued. Job 51554217 is `COMPLETED` with two of its 17 steps killed:

```
$ sacct -j 51554217 -P -o JobID,State,ExitCode,DerivedExitCode
JobID|State|ExitCode|DerivedExitCode
51554217|COMPLETED|0:0|0:9
51554217.batch|COMPLETED|0:0|
51554217.extern|COMPLETED|0:0|
51554217.0|COMPLETED|0:0|
...
51554217.10|CANCELLED by 940740146|0:9|
51554217.11|COMPLETED|0:0|
...
51554217.14|CANCELLED by 940740146|0:9|

$ slurmpast 51554217 --plain --no-logs
job 51554217  COMPLETED
  ...
  filesystem
    read             17.2 MiB                        written          237.4 KiB
    rate             16.5 KiB/s sustained

  nothing to flag.
```

No `outcome` section at all — the tool read the roll-up that says a step was
SIGKILLed and then published a job with nothing to say about it.

**168 parent rows** in the 90-day window carry a non-zero signal in
`DerivedExitCode`, and slurmpast said nothing about the signal on any of them:

```
$ sacct -u youzhi -S now-90days -P -o JobID,State,ExitCode,DerivedExitCode \
    | awk -F'|' '$4 ~ /:[1-9]/' | awk -F'|' '{print $2"|"$3"|"$4}' | sort | uniq -c | sort -rn
    118 COMPLETED|0:0|0:9
     38 CANCELLED by 940740146|0:0|0:9
      5 TIMEOUT|0:0|0:9
      2 OUT_OF_MEMORY|0:125|0:9
      2 FAILED|1:0|0:9
      1 CANCELLED by 940740146|0:0|0:15
      1 CANCELLED by 0|0:0|0:9
      1 CANCELLED by 0|0:0|0:125
```

Five of the 118 are array elements (`53231979_108`, `53231979_111`, `53270913_47`
…), which matters because an array is where nobody reads every element by hand.

The `FAILED|1:0|0:9` pair is the worse half, and it is the reason this is not
merely a missing row. There the gate *did* fire, because `0 != 1` — and printed
the code half alone:

```
$ slurmpast 52428481 --plain --no-logs        # before
  outcome
    exit code        1                               worst step exit  0
```

`worst step exit 0` beside `exit code 1` reads as *the steps were all fine, the
job's own status is the problem*. That is not an absent claim, it is a wrong one.

**The fix.** `Job` gains `derived_signal` beside `derived_exit_code`;
`sacct.py` keeps both halves; the gate compares the **pair** against the job's own
pair, so the row earns its place exactly when the roll-up says something the job's
outcome does not:

```python
derived = (job.derived_exit_code, job.derived_signal)
if derived != (None, None) and derived != (job.exit_code, job.signal):
    outcome.append(("worst step exit", exit_pair_text(*derived), None))
```

`derived_exit_code`'s meaning is deliberately unchanged — it is still the code
half and still an `int | None` — so nothing that already read it moves.

`exit_pair_text` is new and shared, because the `outcome` table now draws two
`code:signal` pairs and a signal that rendered as `0 (signal 9)` on one row and a
bare `0` on the other would be the drift `render.py` exists to prevent. The job's
own `exit code` row was rebuilt on it and reads exactly as round forty-four left
it, `0 (signal 125)` on an OOM included — 125 is Slurm's OOM marker in the signal
half, not a signal, and reusing the one formatter is what keeps the two rows
saying it the same way.

After, on all four shapes the cluster actually holds:

```
$ slurmpast 51554217 --plain --no-logs        # COMPLETED|0:0|0:9
  outcome
    worst step exit  0 (signal 9)

$ slurmpast 52428481 --plain --no-logs        # FAILED|1:0|0:9
  outcome
    exit code        1                               worst step exit  0 (signal 9)

$ slurmpast 52458296 --plain --no-logs        # OUT_OF_MEMORY|0:125|0:9
  outcome
    exit code        0 (signal 125)                  worst step exit  0 (signal 9)

$ slurmpast 52055315 --plain --no-logs        # CANCELLED by 940740146|0:0|0:15
  outcome
    worst step exit  0 (signal 15)                   reason           Prolog
```

`render.job_sections` is the only site changed for the surface because it is the
only site that draws it: the dashboard's detail pane and `--plain` both read that
function.

### What a user sees change

* **The `worst step exit` row is strictly additive.** Every job that drew it before
  still draws it, and nothing new is suppressed: the old gate fired whenever the
  code halves differed, and a differing code half still makes the pairs differ. It
  now *also* fires when only the signal half differs — 168 rows in this window —
  and where it printed a bare `0` next to a non-zero status it now names the signal.
  A roll-up that merely repeats the job's own pair is still hidden, so a clean job
  gains nothing.
* **`--json` gains `outcome.derived_signal`.** A payload is **103** job-level values
  where it was 102; `README.md` and `docs/details.md` are updated, and
  `test_the_documented_value_count_is_the_real_one` holds both to it. It is emitted
  rather than exempted as recoverable, because it is not recoverable: `steps` carries
  the per-step signals only while the steps are there, and `DerivedExitCode` is the
  job row's own field, which outlives a step purge that empties that array.
* The other non-test edit is the README test badge, 2052 → 2060.

### The tests

`tests/test_extraction.py::TestTheSignalHalfOfDerivedExitCode`, eight of them —
four that fail before the fix and four controls that pass in both states.

The four: the pair off the wire through `sacct.parse` (not `_replace`, so the
`0:0|0:9` string is exercised as sacct writes it); the `outcome` row on the
`COMPLETED|0:0|0:9` shape; the row on `FAILED|1:0|0:9`, which pins the *wrong*
value the old gate printed rather than only its absence; and `derived_signal` in
the `--json` payload.

The controls, written against this suite's recorded failure mode of a test that
pins the buggy value:

* a roll-up that repeats the job (`0:0` under `0:0`) still draws **no** row — the
  direction this fix could have been written wrong is "print the field whenever it
  is there";
* `DerivedExitCode=2:0` still reads as the bare `2` it always did, which is
  `derived_exit_code`'s unchanged meaning held to its rendered form;
* an unrecorded roll-up stays `(None, None)` and draws no row, never a printed
  `signal None`;
* the job's own `exit code` row still reads `0 (signal 125)`, which is the control
  for folding both rows into one formatter.

Teeth, in two stages, neutering only what this round added and restoring from a
copy rather than from HEAD. Reverting all three layers to the pre-fix state — the
discarded half, the code-only gate, the payload key removed — fails exactly the
four and passes exactly the four controls. Reverting **only** the `render.py` gate,
with `sacct.py` still keeping the signal, fails the two surface tests and leaves
the extraction and payload tests green, so each layer is independently pinned.

### Still open

Carried forward from round forty-four, looked at and deliberately not touched in a
one-fix round: **`site.gpu_utilization_note` treats `None` as False**, asserting
"not gathered by this cluster (needs AutoDetect=nvml in gres.conf)" from the
absence of `AccountingStorageTRES` rather than from a reading of it. Still not
reproducible here, since this cluster publishes the TRES list.

Fully addressed: the defect above, at every site of it — extraction, model, both
text surfaces via `render`, and `--json`. Nothing withdrawn.

## Round forty-four — the half of ExitCode after the colon, and who cancelled it

Two defects, both fixed, both in `diagnose` — the module that turns a finished job
into "here is what went wrong", and the one this session had not looked at. Each
was found by reading the tool's answer against `sacct`'s own record for the same
job, over 50,616 real rows. 2026 tests before, **2052** here; all four gates clean.

### 1. `ExitCode` is `code:signal`, and only the code was read

`src/slurmpast/diagnose.py:778` (`_exit_rules`) and `src/slurmpast/render.py:1492`
(`job_sections`).

Slurm spells a signal kill with a **zero** code — `0:15` — so the rule written as
`signal == 9 or code == 137` named SIGKILL and nothing else, and the `outcome`
table's `if job.exit_code:` hid the row on exactly the jobs it had something to
say about. SIGTERM is the signal a supervisor sends *first*: `timeout`, a shell
trap, a watchdog, a queue system layered over Slurm.

Measured, not argued. Three parent rows in this cluster's 90-day history are
`FAILED` at `0:15`, and this was the whole report about one of them:

```
$ sacct -j 53412513 -P -o State,ExitCode,Elapsed,Timelimit,TotalCPU
State|ExitCode|Elapsed|Timelimit|TotalCPU
FAILED|0:15|00:18:46|00:20:00|00:01.595

$ slurmpast 53412513 --plain --no-logs
  ...
  findings

  [FAIL] Allocation did essentially nothing
        00:18:46 of wall clock, 1.6s of CPU, holding 1 GPU(s). ...
        → Find the blocking call — or the work, if it ran in a detached pool ...
```

No `outcome` section at all, and the only guidance on screen sent the reader to
hunt a blocking call in their own code for a job **something outside it had
terminated**. That is the identical defect NODE_FAIL, BOOT_FAIL and DEADLINE were
each given a finding for in round eighteen — "`BOOT_FAIL` and `DEADLINE` were in
no rule at all, so a node that never booted was told to find its blocking call."

After:

```
$ slurmpast 53412513 --plain --no-logs
  outcome
    exit code        0 (signal 15)
  ...
  [FAIL] Killed by SIGTERM
        Exit signal 15, and nothing in the accounting record accounts for it: the
        state is FAILED, not OUT_OF_MEMORY, TIMEOUT, CANCELLED, PREEMPTED or
        NODE_FAIL, each of which would name its own killer.
        → Look for a wrapper or watchdog killing it — a queue system layered over
          Slurm, a `timeout` in the batch script, or the node's own OOM killer ...
```

The suppression set and the action carry over **unaltered**, because their
reasoning does: Slurm sends SIGTERM *before* SIGKILL on `scancel`, the wall clock,
an eviction and a cgroup OOM, so on those five states neither signal carries
anything the state has not already given. `code == 137` stays its own arm — that is
the shell's 128+9, which a wrapper can propagate as the status with no signal
beside it — and `sigkill` keeps its finding code for signal 9 so no `--json`
consumer sees a rename. The signals it never covered get `signal-kill`.

`_signal_name` is a table, not `signal.Signals(n).name`: that raises `ValueError`
for a number the platform does not define, and this cluster's accounting holds a
record with signal 40.

Two smaller sites of the same root cause went with it. `named_above` in the no-log
branch was keyed on `signal == 9`, so a `3:15` job would have been handed "an exit
status does not name a cause" directly under "Killed by SIGTERM" — the
self-contradiction round eighteen's third finding closed and that comment exists
to hold. And the `outcome` row is now `if job.exit_code or job.signal:`, which
also un-hides the `0 (signal 125)` of every `OUT_OF_MEMORY` job — 122 parent rows
in this window, each of which showed
no exit code anywhere while `sacct -o ExitCode` printed one. It lands in
`render.py` rather than in `report.py` and `tui.py`, per this repo's rule, so both
surfaces gained the row at once.

**Why the suite read as working.** Every existing signal test builds
`exit_code=137, signal=9` — the *shell's* 128+9 convention, which sacct on this
cluster never writes. The one shape real accounting uses, `0:<signal>`, had no
test, so the rule was only ever exercised on a value where the code was non-zero
too.

### 2. `CANCELLED by <uid>` was preserved and never read

`src/slurmpast/diagnose.py:649` (`_exit_rules`), with the new reader at
`diagnose.py:615`.

`sacct._canonical_state` keeps that suffix on purpose, and says why: "`Job.state`
carries it, `Job.base_state` drops it, and **both are read**." Nothing read it. So
a job an administrator killed drew the sentence written for the submitter's own
two possibilities, and neither of them was true:

```
$ sacct -j 53439966 -P -o State,Elapsed,Timelimit,UID
State|Elapsed|Timelimit|UID
CANCELLED by 0|3-03:08:11|10-00:00:00|940740146

$ slurmpast 53439966 --plain --no-logs
  [INFO] Cancelled, not failed
        A deliberate kill and an abandoned run are identical in accounting, so
        this is excluded from failure statistics.
```

A three-day reservation that root ended, reported as though its owner had done it.
Three jobs in the 90-day window are `CANCELLED by 0`. After:

```
  [INFO] Cancelled by root, not by you
        sacct records this as CANCELLED by 0 — root — while the job belongs to uid
        940740146. An administrator or the scheduler ended it, so how far it got
        says nothing about whether the job was healthy.
        → Nothing in the script chose this. Look for a maintenance window, a policy
          or QOS limit, or a dependency that could never be satisfied before
          resubmitting it unchanged.
```

Claimed only when **both** uids are on the record and they differ. An empty `UID`
means the comparison cannot be made, not that it came back False — the rule
`site.py` states for a missing configuration fact — and the ordinary
self-cancellation — 1,087 of the 1,090 cancelled parent rows here — keeps its
wording, its `cancelled` code and its empty action untouched, which
`test_audit`'s actionless-arrow class depends on.
`_cancelled_by` accepts only the exact three-token numeric shape, so a canceller is
never guessed at from a spelling it does not know. Severity stays INFO: a CRITICAL
here would make `slurmpast <jobid>` exit 1 on a run `theme.STATE_HEALTH`
deliberately declines to colour red.

### What now pins it

`tests/test_diagnose.py`, `TestTheSignalHalfOfExitCodeIsRead` (17) and
`TestWhoCancelledIt` (9) — 26 tests. Two of them go through `sacct.parse` from a
real `0:15` / `CANCELLED by 0` row rather than `_replace`, because a `_replace`
test is what let defect 1 hide behind the 128+9 convention.

```
$ pytest tests/test_diagnose.py -k "TheSignalHalfOfExitCode or WhoCancelledIt"
26 passed, 110 deselected

# `killer` restored to `9 if (signal == 9 or code == 137) else None`
4 failed, 22 passed        # SIGTERM, the parsed 0:15 row, signal 40, the no-log agreement
# `_signal_name` restored to `signal.Signals(number).name`
1 failed, 25 passed        # ValueError on signal 40
# `named_above` restored to `signal == 9`
1 failed, 25 passed
# render's outcome row restored to `if job.exit_code:`
1 failed, 25 passed
# the `exit_code is None` guard on that row removed
1 failed, 25 passed
# the who-cancelled branch neutered
3 failed, 23 passed
```

Every control passes in **both** states, and three of them fail on a *wrong* fix
rather than on the absence of one, which is the shape round five went looking for:

* **`test_an_absent_owner_uid_makes_no_claim`** and
  **`test_your_own_scancel_keeps_its_wording_and_its_empty_action`** — written
  `if canceller:` (fire on the suffix alone, skip the uid comparison), both fail.
  That version announces a stranger's `scancel` on every cancelled job and passes
  every other test here.
* **`test_a_suffix_that_is_not_a_uid_makes_no_claim`** — with the `.isdigit()`
  shape check dropped, `CANCELLED by root` and `CANCELLED by +` fail.
* **`test_signal_nine_keeps_its_finding_code_and_its_wording`**, and
  **`test_exit_137_with_no_signal_recorded_still_fires_as_sigkill`** — the case the
  old rule *did* cover, pinned by code, title and evidence so broadening it cannot
  rename what `--json` publishes or drop the 137 arm.
* **`test_a_job_with_no_signal_draws_no_kill_finding`** (`0` and `None`) and
  **`test_a_clean_job_still_has_no_exit_code_row`** — the two ways `if signal` and
  `or job.signal` could have been written too loosely.
* **`test_the_state_that_explains_the_kill_still_wins`** (five states) and
  **`test_out_of_memorys_own_marker_signal_is_suppressed_too`** — the broadened
  rule inherits the suppression, so no cancelled or OOM-killed job gains a CRITICAL.

### Numbers a user might be depending on

* A finished job whose `ExitCode` records a signal now shows an `exit code` row on
  both surfaces where it previously showed none: `0 (signal 15)`, `0 (signal 125)`.
  No figure changed — a row that was suppressed is now printed.
* A `FAILED` job with a non-zero signal gains one finding, `signal-kill`, at
  CRITICAL. On the 90-day window that is 3 jobs. Since `Job.failed` already
  counted them, the exit code of `slurmpast <jobid>` does not change for any of
  them.
* A cancelled job whose canceller differs from its owner swaps `cancelled` for
  `cancelled-by-other`, same INFO severity. 3 jobs here. Anything self-cancelled or
  with no `UID` on the record is byte-identical to before.
* The other non-test edit is the README test badge, 2026 → 2052.

### Looked at and found sound

Recorded because a clean result is worth the same as a defect next round. All
checked by running the code, on real records where one exists:

* **`OUT_OF_MEMORY` with a MaxRSS below the limit** — the case where the cgroup
  killed it on a spike the sampler never saw. Correct already, and it says so in
  the right direction: job 50488041, `MaxRSS 68.0 GiB` against a 100.0 GiB limit,
  gets "the kill is proof the peak reached it: treat the sample as a floor" plus
  "the sampler runs every 30s and the job ran 98s, so at most 4 samples". The
  over-report caveat every *other* MaxRSS sentence carries is deliberately not
  reused there.
* **`TIMEOUT` on a job that consumed almost no CPU** — `timeout-hang`, with "Do NOT
  raise --time; a longer limit buys a longer hang". This is the tool's founding
  correction and it holds.
* **`NODE_FAIL`, `BOOT_FAIL`, `DEADLINE`, `PREEMPTED`** — each has its own finding
  and each suppresses every rule that reads the CPU total.
* **Boundary arithmetic.** `Elapsed=0` COMPLETED, an empty `MaxRSS` on an OOM
  (very common — the entire `MaxRSS` column is empty on the parent row here),
  `MaxRSS` exactly equal to the limit under both `OUT_OF_MEMORY` and `COMPLETED`,
  and a single-task step. No division by zero, no finding fired off a value it
  could not have, and `rss-above-limit` is a strict `>` so equality is not "above".
* **`site.py` against this cluster's own configuration.** `scontrol show config`
  gives `JobAcctGatherType=jobacct_gather/linux`, `JobAcctGatherFrequency=30`,
  `AccountingStorageTRES=...,gres/gpu` and `SLURM_VERSION=20.11.8`; `_parse_config`
  reads all four correctly, `rss_from_cgroup` is False (so the process-tree caveat
  is the earned wording, not the pessimistic default), `sampling_seconds` is 30,
  `tracks_gpu` is True and `tracks_gpu_utilization` is False. The
  `Key = value` split survives the three lines in that output whose value contains
  a second `=` (`GpuFreqDef`, `Licenses`, `SchedulerParameters`), and no key in the
  227 lines appears twice, so last-write-wins is not reachable here.
  `partition_ceiling` returns `(128, 250000)` for `amd`, which matches
  `scontrol show partition amd` (40 nodes, `TotalCPUs=5120`).

### Left open

Neither was fixed, both are recorded rather than argued, and both are outside a
two-fix round:

* **`DerivedExitCode`'s signal is discarded**, so a step killed inside a job Slurm
  called COMPLETED is invisible. `sacct.py:854` reads `derived_code, _ =
  _parse_exit(...)`, and `render.py:1515` then gates the `worst step exit` row on
  `derived_exit_code not in (None, job.exit_code)` — `0` against `0`, so nothing is
  drawn. Real: job 51554217 is `COMPLETED|0:0|0:9`, and two of its 17 steps are
  `CANCELLED by 940740146` at `0:9`. **118 parent rows** in this window are
  `COMPLETED|0:0|0:9`, array elements among them, and slurmpast says nothing about
  any of them. Closing it needs a `derived_signal` field on `Job`, so it is a round
  of its own.
* **`site.gpu_utilization_note` treats `None` as False.** `tracks_gpu_utilization`
  returns None when `AccountingStorageTRES` is absent, and the function then falls
  through to *"not gathered by this cluster (needs AutoDetect=nvml in gres.conf)"* —
  asserting a site cause from a fact it does not have, against this module's own
  stated rule that "every caller must treat None as 'cannot say' rather than as a
  default". Not reproducible here (this cluster publishes the TRES list), and the
  path is narrow, which is why it is written down rather than changed on a guess.

Fully addressed: both defects above, at every site of each. Nothing withdrawn.

## Round forty-three — a unit ladder that printed 1024.0

One defect, fixed, in `duration.format_bytes`. It chose the unit from the raw
value and then rounded the figure, so a value just under a boundary printed
`1024.0 MiB` — which means the ladder failed, since the whole point of taking the
largest unit above 1 is to stay *below* 1024. 2017 tests before, **2026** here;
all four gates clean.

### The defect

`src/slurmpast/duration.py`. The loop compared `value >= scale` and then formatted
with `%.1f`. Those two steps disagree in a narrow band below every boundary:
`1073692672` is 24 bytes short of 1 GiB, so MiB was selected, and `%.1f` of
`1023.99969…` reads `1024.0`.

Measured, not argued — that value is a real `MaxRSS`:

```
$ sacct -u youzhi -S now-90days -P -o MaxRSS,ReqMem,AveRSS   # 13,426 distinct byte values
   values that render as "1024.0 <unit>": 1
     1073692672  ->  1024.0 MiB
```

One in 13,426 is rare, and it is not hypothetical: the band is 0.0049% of each
unit, so it is hit about once per twenty thousand arbitrary values, and this
window produced one.

**The sibling tool had already solved it.** `slurmwatch.units.format_bytes` carries
the case as its A5 with the reason in the comment — *"a number just under a
boundary promotes to the next unit instead of printing '1024.0 MiB': e.g.
1073741800 … must read 1.0 GiB"* — and on that exact input the two tools
disagreed, `1024.0 MiB` against `1.0 GiB`. Same owner, same cluster, same
quantity.

The fix promotes as soon as the figure would round up, at `scale * 1023.95 / 1024`
(where `%.1f` flips). The threshold is deliberately *not* "the figure rounds to
1.0", which would take `1000 B` to `1.0 KiB` and break the byte floor this
docstring promises.

### The same defect at the ceiling

With `TiB` as the top tier there was no unit to promote into, so everything from
~1024 TiB up read `1024.0 TiB`, `2048.0 TiB`. No job has a petabyte of RAM — but
`read_bytes`, `write_bytes` and `io_rate` come through this function too, and the
largest real value in the same window is **30.9 TiB of disk read**, which puts
1 PiB a factor of 33 away rather than out of reach. A `PiB` tier was added, which
is also what the sibling tool has. `1024.0 PiB` (1 EiB) remains the ceiling, as it
is there.

### What now pins it

`tests/test_duration.py`, `TestTheUnitLadderNeverPrintsAFigureOfTenTwentyFour` —
nine tests. The load-bearing one is a **swept property**, not a spot check: across
`2**10 … 2**59`, no value may print a figure of 1024.0 or more in any unit below
the PiB ceiling. Stated that way, a later change to the tier list or the format
string cannot reintroduce this at one tier while fixing another.

```
$ python -m pytest tests/test_duration.py -k UnitLadderNeverPrints -q
9 passed, 60 deselected

# `value >= scale` restored
7 failed, 2 passed        # every promotion, the sweep, and the cross-tool check

# the PiB tier removed
3 failed, 6 passed        # the ceiling case, the sweep, the cross-tool check
```

Both controls pass in **both** states, and they are the two ways this fix could
have been written wrong:

* **the byte floor** — `0 B`, `1 B`, `1000 B`, `1023 B`. A promotion rule keyed on
  "the figure rounds to 1.0" satisfies every other test here and silently converts
  `1000 B` into `1.0 KiB`.
* **the ordinary figures** — `1.0 KiB`, `1.5 KiB`, `200.0 MiB`, `4.0 GiB`,
  `30.9 TiB`, `n/a`. Nothing away from a boundary moved.

A ninth test compares this function against `slurmwatch.units.format_bytes`
directly and skips if that checkout is absent — it is a sibling, not a dependency.

### Numbers a user might be depending on

Any figure that previously read `1024.0 X` now reads `1.0 <next unit>`; figures
above ~1024 TiB now read in PiB. Nothing else changed — no threshold, no
measurement, no ranking. The other non-test edit is the README test badge,
2017 → 2026.

### Looked at and found sound

Recorded because a clean result is worth the same as a defect next round:

* **`sizing`'s zero boundaries.** `_round_walltime(0)` returns `0`, and
  `--time=0` is *unlimited* per sbatch's own man page — "A time limit of zero
  requests that no time limit be imposed" — which would be the opposite of
  right-sizing. It is unreachable: `walltime_advice` filters on
  `j.completed and j.elapsed`, a truthiness test, so a zero-elapsed run never
  reaches the arithmetic. `memory_advice` guards `j.max_rss` the same way, and
  `_round_gib` uses `ceil`, so a positive figure floors at 1 GiB. All three advice
  paths are sound at zero.
* **`parse_duration` against `ElapsedRaw`** — Slurm's own integer answer — over
  **50,604 real rows**: 0 mismatches, and 0 against an independent parser across
  3,034 distinct values. Every `DD-HH:MM:SS` Timelimit form up to `30-00:00:00`
  parses correctly.

Fully addressed: the `1024.0` defect at every tier and at the ceiling. Nothing
withdrawn, nothing left open from this round.

## Round forty-two — an arrow pointing at nothing, on the one surface with no guard

One defect, fixed. `--patterns` drew the action arrow for a finding that has no
action, so its last line was a bare `→` with nothing after it. 2012 tests before,
**2017** here; all four gates clean.

### The defect

`report.py:758`, in `render_patterns`. The job report had carried the guard for this
exact case at `report.py:475` — emit the `→` block only `if finding.action` — and the
patterns surface did not, so it wrapped and indented an empty string and printed the
arrow that introduces it.

Two findings reach it, and neither is exotic: the *"%d further groups show the same
repeat-failure pattern"* tail counter and the requeue tail both carry `action=""` by
construction. The tail counter is the **last** line of `--patterns` whenever there
are more repeat-failure groups than the surface lists, which is the normal state on
a busy account — so the ordinary reading of that screen ends on an arrow pointing
at nothing.

Rendered, with the guard removed and nothing else touched:

```
        8 of 10 runs of rc-tok-github_code in test failed; 8 were OUT_OF_MEMORY.
        ... or per job with `slurmpast <jobid>`.
        →
```

```
$ python -m pytest tests/test_audit.py -k AnArrowIsOnlyDrawn -q   # guard removed
E       assert not ['        → ']
FAILED tests/test_audit.py::TestAnArrowIsOnlyDrawnWhenItPointsAtSomething::test_the_patterns_tail_counter_draws_no_arrow
1 failed, 4 passed, 66 deselected
```

Not reachable from `--demo`: its synthetic history has too few repeat-failure
groups to produce the tail, which is why the screen looks clean there and why the
test builds the history rather than leaning on the demo. That is also the honest
answer to "why did nobody see it" — the surface that shows it is the one nobody
renders when checking a change by eye.

### What now pins it

`tests/test_audit.py`, `TestAnArrowIsOnlyDrawnWhenItPointsAtSomething` — five tests,
of which three exist to stop the fix from being narrower or wider than the defect:

* the job report draws no arrow for an actionless finding (the side that was always
  right, so a regression there is caught too);
* the `--patterns` tail counter draws no arrow — the defect;
* **both surfaces agree** on the same actionless finding, which is the property
  `render.py` exists to hold and the one that was broken;
* **control** — a finding that *does* have an action still gets its arrow, so
  "never draw arrows" does not pass;
* **control** — the guard is the same test on both sides, so the two cannot drift
  apart again by one being tightened alone.

Teeth measured rather than argued: with only the `render_patterns` guard removed and
the job report's left in place, exactly one of the five fails and the four controls
pass. Both directions were run, so the controls are known not to be mirrors of the
fix.

### This is Round forty-one's shape, one layer down

Round forty-one recorded a fix that *landed* on two surfaces and was *tested* on
one. This is the same family with the earlier verb: a guard that was *written* for
one surface and never carried to the other, on a repo whose `render.py` exists
precisely so "the dashboard and `--plain` cannot drift". The recurring failure is
not the arrow; it is that a per-surface change is still easy to make here without
anything asking whether the other surface needs it. The fifth test above is a small
standing answer to that — it compares the two guards rather than each in isolation.

### Numbers a user might be depending on

No measurement, threshold or ranking changed — the fix removes a line of output and
adds none. The only non-test edits are `report.py:758` and the README test badge,
2012 → 2017.

Fully addressed: the actionless-arrow defect on both surfaces. Nothing withdrawn,
nothing left open from this round.

## Round forty-one — the fix that landed on both surfaces and was tested on one

No new defect in the product. One test gap, in the working tree's own
`render.gpu_hours_equivalence` fix: it changed **two** surfaces and shipped a test
for **one** of them. 2008 tests before, **2012** here; all four gates clean.

### The gap

`render.py` states its own reason for existing — *"the dashboard and `--plain`
cannot drift"* — and the GPU/CPU-hour exchange rate is the fact that proved the
rule. `report.py` had carried a comment claiming *"the dashboard puts the same two
facts under `?`"*, and half of it was untrue: the digit fold was under `?`, the rate
never was. So the dashboard ranked every workload it listed by a weighting it named
nowhere, while a paste of the same table explained itself.

The fix was right — one function in `render.py`, placed by `report.py:603` as a
caption and by `tui.py:724` as a help note — but only the caption half was pinned.
`tests/test_readability.py`'s
`test_plain_report_explains_the_ranking_without_the_jargon` asserts the rate is in
the `--plain` head; nothing anywhere mentioned the help note. Measured rather than
argued: with `tui.py:724` reverted to its pre-fix text and nothing else touched, the
only tests that notice are the ones added this round —

```
$ python -m pytest -q            # help note reverted
FAILED tests/test_readability.py::TestOneExchangeRateAcrossBothSurfaces::test_the_dashboard_quotes_the_rate_the_plain_caption_does
FAILED tests/test_readability.py::TestOneExchangeRateAcrossBothSurfaces::test_they_still_agree_with_a_real_record_in_the_history
FAILED tests/test_readability.py::TestOneExchangeRateAcrossBothSurfaces::test_the_comparison_can_see_the_two_surfaces_drift
3 failed, 2009 passed in 245.14s (0:04:05)
```

— so before this round the same revert was 2008 passed and green. That is this
repo's named recurring shape, "fixed only on one side", applied to the test rather
than to the fix.

### What now pins it

`tests/test_readability.py:1935`, `TestOneExchangeRateAcrossBothSurfaces` — four
tests. They render the same content through both front ends (`--plain` through
`render_overview`, the dashboard headlessly through Textual's `run_test()` and `?`)
and compare the rate as **facts** — `(number, unit, number, unit)` — rather than as
a sentence, so a wrap or a rephrasing does not matter and a number or a unit does:

* the two surfaces quote the same rate, and it is the one
  `render.gpu_hours_equivalence()` returns, on `--demo`'s fixed history;
* they still agree with a real record in the history (job 51170455 as `sacct`
  reported it — 3 GPUs for 1h52m, so it moves both hour columns);
* **control** — move `--plain` off the shared string and the comparison must fail;
  without it `plain == dashboard` would pass just as happily on two `None`s;
* **control** — `--plain`'s caption follows `GPU_CORE_EQUIVALENT`, not a literal
  that happens to read 16.

Teeth, measured both ways rather than argued:

```
$ python -m pytest tests/test_readability.py -k ExchangeRateAcrossBoth -q
4 passed, 144 deselected

# tui.py:724 reverted to its pre-fix text
3 failed, 144 deselected      # "the dashboard names no exchange rate"

# render.gpu_hours_equivalence returning a hardcoded "16 CPU-hours"
1 failed, 3 passed            # the constant-follows control
```

Verified on live data as well as on the demo: against midway3's real 30-day
history (13,107 job records) both surfaces quote `1 GPU-hour = 16 CPU-hours`.

### Two nits reported, not changed

Both are in the help note, both are cosmetic, and neither is a wrong number:

* **The rate wraps between its quantity and its unit.** The help box is clamped to
  78 columns, so at *every* terminal width the note breaks as `... Weighted at 1` /
  `GPU-hour = 16 CPU-hours.` — a figure separated from what it is a figure of, which
  is the family of defect rounds six and seven spent two passes on. The fact-based
  comparison above is deliberately indifferent to it.
* **The two surfaces are conditional on different things.** `--plain` prints the
  rate only when a GPU column is on screen (asserted by
  `test_a_cpu_only_history_is_not_told_the_exchange_rate`); the dashboard's note
  states it unconditionally, including on a CPU-only history where the GPU-HOURS
  column is hidden. Defensible as it stands — the help screen is a static reference
  sheet rather than a caption over one table — so it is recorded here rather than
  "fixed" into a screen that changes its own documentation.

### Numbers a user might be depending on

None changed. No behaviour was touched this round; the only non-test edit is the
README test badge, 2008 → 2012.

## Round forty — a task imbalance measured across two steps

One defect, in the multi-step rollup: how a job's `.batch` / `.extern` / `.<n>`
rows are combined into one record. Found by running the working tree against
midway3's real 30-day accounting history — 43,133 `sacct` rows, 13,118 job
records — and then against the per-job query for the record it implicated.
2004 tests before, **2008** here; all four gates clean.

### The rollup questions that came back clean

The round began by asking whether a step's figure can be double-counted or
silently dropped. Each answer below was measured on the live database, not read
off the source:

* **`TotalCPU` sums the work steps, and the sum is Slurm's own.** Over the
  13,081 records carrying both, `sum(work steps) / allocation TotalCPU` is
  **0.999 at the 5th percentile, 1.000 at the median, 1.000 at the 95th**; the
  extremes are 1.0002 high and one record low. **0** records exceed 1.05, so
  nothing is added twice — `_from_steps`' claim in `model.py:466` still holds.
* **Step attachment is positional, and this cluster's emission order supports
  it.** `sacct -D` sorts globally by `Submit`, so an incarnation's steps follow
  its allocation row even for a requeue: all 7 multi-incarnation ids in the
  window (three of them arrays, one requeued twice) emit in that shape. **0**
  duplicate `(JobID, Submit)` allocation keys and **0** duplicate step rows in
  43,133 — the `open_key` overwrite in `sacct.py:944` cannot merge two
  incarnations' step lists on data this cluster produces.
* **No step outruns the allocation row's node count.** 0 of 13,118 records have
  a step reporting more `NNodes` than `Job.node_count`.
* **`MaxRSS` attribution is clean.** 0 records name a peak node or task for a
  peak they do not have (`MaxRSSNode` is empty on every row whose `MaxRSS` is),
  0 have two steps tying on the peak with different node names, and the
  extern-is-impossible drop rule in `max_rss` fired on exactly 1 job.

`Elapsed` is read from the allocation row only and is not summed anywhere, so
there is nothing to double-count.

### The defect: `rss_task_imbalance` divided two populations

`model.py:776`. The property is documented as a per-task statement — "above 1
means one task holds far more than its peers" — and it was computed as
`Job.max_rss / Job.ave_rss`. Those two are not the same population:
`max_rss` is the largest `MaxRSS` over every measured step **including
`.extern`**, while `ave_rss` is the largest `AveRSS` over the **work steps
only**. Round eighty-one routed both through `measured_steps` and wrote down the
intent — *"the ratios built from them are now ratios of one population"* — but
the extern asymmetry and the free choice of step survived it.

Reproduced on job 52853137 (`slurmpast 52853137`, working tree before the fix):

```
  memory
    peak on          midway3-0455 task 0
    average          53.7 MiB (190.7x the average)

  [INFO] Memory use is uneven across tasks
        Peak task held 10.0 GiB against a 53.7 MiB average (190.7x). The job's memory
        ceiling has to cover the largest task, not the mean.
```

`--json` carried `"task_imbalance": 190.67493273216493`. No task did that. The
10.0 GiB is the `.extern` container step; the 53.7 MiB is `AveRSS` on step
`.20`, a different set of processes. Extern's own two figures do not even agree
with each other:

```
$ sacct -D -j 52853137 --format=JobID,State,NTasks,MaxRSS,AveRSS --parsable2
52853137.extern|COMPLETED|1|10487884K|18607848K
52853137.2|COMPLETED|4|6496K|3166K
```

— an average 1.8x the peak it is supposed to sit under. The job's one genuinely
multi-task step is `.2`, and its real imbalance is 6496K against a 3166K mean
across 4 tasks: **2.05x**.

Fixed by measuring the ratio inside one step and taking the widest, `.extern`
excluded. No task-count gate is needed and none was added: Slurm reports
`MaxRSS == AveRSS` on a single-task step, so such a step contributes exactly 1.0
and cannot raise the figure — which is also why the property still answers on a
one-step job, where it always did.

Two call sites had to follow, because both printed the ratio beside the pair it
is no longer built from:

* `diagnose.py:1095` — the evidence quoted `format_bytes(job.max_rss)` and
  `format_bytes(job.ave_rss)`. It now quotes the ratio and the task count only,
  the shape the `straggler` finding directly above it already uses.
* `render.py:1404` — the memory block's `average` row carried
  `"   (%.1fx the average)"`, which read as a ratio of the two figures on screen
  and was not one. Dropped; the finding carries the ratio, where the text can say
  which population it covers.

After, on the same job: `"task_imbalance": 2.0518003790271635`, and

```
  memory
    peak on          midway3-0455 task 0             average          53.7 MiB

  [INFO] Memory use is uneven across tasks
        One task held 2.1x the mean of its peers inside a single step, across 4 tasks.
        The job's memory ceiling has to cover the largest task, not the mean.
```

**What changes in the numbers.** `--json`'s `memory.task_imbalance` changes on
**16 of 13,118** records in this window (190.7 -> 1.0 on 52853137's clipped
form, 25.8 -> 1.0, 8.1 -> 1.0, 7.1 -> 1.0, and so on; one moves up, 1.3 -> 1.49);
the other 13,065 that carry a figure are unchanged, and **0** records lose their
figure. `memory.peak_bytes` and `memory.average_bytes` are untouched. The
`task-memory-imbalance` finding fires on the same jobs in this window, with a
different number and different text. On screen the `average` row loses its
parenthetical, which no test or committed asset asserted.

### Reported, not changed

* **`_io_from_steps` (`model.py:909`) does not apply the in-progress filter its
  CPU sibling applies.** For a RUNNING job, `_from_steps`, `max_rss`, `ave_rss`,
  `max_vmsize`, `max_pages` and `rss_step_spread` all restrict to
  `measured_steps`; the disk sum takes every work step. Measured: job 56352671
  (RUNNING) reports 123.7 GiB read and `1.0 MiB/s sustained` with **100%** of it
  from the 107 steps that have already exited, on the same screen where memory
  and CPU say they cannot be measured yet — likewise 53834744 at 20.8 GiB from
  80 exited steps. **Examined and left alone deliberately**, because the
  straggler argument does not transfer: the distortion `measured_steps` was
  written against is a *max* or a *ratio* being taken over the wrong population,
  where one short monitor step dominates. A byte *sum* is additive, an
  `srun --overlap` monitor contributes almost nothing to it, and the bytes a
  finished step of a live allocation moved really were moved by that allocation.
  Excluding them would return `None` for every running multi-step job and delete
  a genuine measurement to buy consistency. Not a defect; the asymmetry is worth
  a comment saying so, which this round did not add.
* **`energy_joules` (`model.py:1016`) takes the max over steps where the
  quantity is cumulative** and should be the sum, or the allocation row. Not
  reproducible here — this cluster runs `AcctGatherEnergyType=none`, so the field
  is empty on all 43,133 rows and no test can be written from real output.
* **`_gres_int` (`model.py:1091`) returns `None` for `gpu:4(IDX:0-3)`**, because
  it reads the leading integer of the last colon-separated part and gets `0-3)`.
  Unreachable on any cluster this can be checked against: `sacct` here answers
  `fatal: AllocGRES is deprecated, please use AllocTRES`, so the field is
  dropped by the `--helpformat` negotiation and the pre-20.11 path never runs.
* **`cpu_freq` / `cpu_freq_hz` / `straggler_spread` / `slowest_task` return the
  *first* work step that has a value**, not the step that did the work. On a
  107-step allocation that is whichever step sacct emitted first. `cpu_freq_hz`
  is display-only (`render.py:1343`, no finding reads it); `straggler_spread`
  does feed a WARNING, and it at least stays inside one step, which is the
  property this round's defect lacked.

Nothing was withdrawn. The defect is fully addressed at all three call sites;
the four items above are open as reports.

## Round thirty-nine — one workload, two verdicts; and the name on screen that the search box could not find

Two defects, both in modules no earlier round had opened: `patterns.py` (the
cross-run detectors) and `index.py` (grouping, sorting, filtering). Found by
running the working tree against midway3's real 30-day history — 13,126 records,
13,120 usable, 879 workloads — and against `--demo` for the deterministic cases.
1994 tests before, **2004** here; all four gates clean.

Both defects are the same shape, and it is the shape this repo's own rules single
out: **code that has drifted from a rule it states about itself, so that two
surfaces describe one workload two ways.** Neither is a new feature; both are one
surface being brought back to what another surface already promised.

### Fixed

**1. `patterns.py:306` — the dominant failure state was chosen by count alone, so
a tie fell to the order sacct happened to return the rows — and `index` hands this
function the same group in two different orders.**

`find_repeat_failures` picked the state to report with
`max(states.items(), key=lambda kv: kv[1])`. On a tie, `max` keeps the first item
of the dict, and that dict is filled in the order the records arrive. The two call
sites in `index` do not agree on that order:

```
index.py:491   History.patterns        -> find_repeat_failures(self.jobs)
index.py:499   History.group_patterns  -> find_repeat_failures(group.jobs)
```

`self.jobs` is sacct order; `GroupStats.jobs` was sorted newest-first by
`build_groups`. So one workload of three TIMEOUT and three FAILED runs, in one
session, on one history:

```
PATTERNS PANEL (History.patterns):
    6 of 6 runs of trainer in test failed; 3 were TIMEOUT. Every one used the same --time=00:30:00.
    -> Raise --time above that limit; a timeout's Elapsed only bounds runtime from below.

GROUP DRILL-DOWN (History.group_patterns) for trainer
    6 of 6 runs of trainer in test failed; 3 were FAILED.
    -> Stop resubmitting; the failure is deterministic. Reproduce interactively.

group.jobs order: ['105', '104', '103', '102', '101', '100']
self.jobs order : ['100', '101', '102', '103', '104', '105']
```

Not two phrasings of one verdict — two different actions. "Raise the limit" and
"stop resubmitting, the failure is deterministic" cannot both be the advice, and
which one you get depends on which screen you opened. That is exactly the drift
`render.py` exists to prevent, one layer below `render`.

`find_requeues`, three functions further down the same file, has always broken this
tie on the state name: `key=lambda kv: (kv[1], kv[0])` at `patterns.py:478`. Same
rule, same module, same shape of dict. Fixed by using it here too, so the two
cannot separate again.

No effect on midway3's real data — no qualifying group there has a tied failure
state, and the 30-day `--json` patterns array is byte-for-byte what it was. The
defect is in what happens when one does.

Tests: `TestTheDominantFailureStateDoesNotDependOnRowOrder` in
`tests/test_patterns.py`, four cases. Two behavioural — the finding is identical
forward and reversed, and `History.patterns` agrees with
`History.group_patterns` about one workload, which is the path that actually
disagreed. Two controls, deliberately paired: five TIMEOUT against one FAILED must
still read TIMEOUT (FAILED sorts first alphabetically, so a rule that had stopped
reading the *count* would answer FAILED), and five FAILED against one TIMEOUT must
still read FAILED (so neither half of the key can be dropped without failing one of
the two). Reverting the fix fails both behavioural cases and leaves both controls
passing.

**2. `index.py:440` — the overview printed a job name the search box could not
find, on 639 of 879 real workloads.**

JOB NAME on the overview table is `GroupStats.label` (`report.py:641`), and
`filter_groups` searched `GroupStats.name` — the fold. `label` substitutes a real
job name wherever the fold would otherwise stand in for exactly one, which is the
ordinary case rather than the exception. Measured over the real 30-day history:

```
groups: 879  label != name: 639
groups whose displayed label finds NOTHING: 639
   label=a4-midc                            fold=a#-midc                        part=test runs=56
   label=exp-a45                            fold=exp-a#                         part=test runs=62
   label=cpas_t2o                           fold=cpas_t#o                       part=test runs=20
   label=exp-a35-effort                     fold=exp-a#-effort                  part=test runs=1
   label=a14-dpo                            fold=a#-dpo                         part=test runs=19
```

Three rows in four: the table says `exp-a45`, you type `exp-a45`, you get an empty
list. `filter_jobs` names this failure in its own comment forty lines above —
"typing what you can plainly see and getting an empty list is the worst kind of
empty result — it reads as missing data" — and round thirty-one fixed the same
class of thing for hostnames. Round thirteen fixed the *promise* this box makes
(`GROUP_SEARCH_FIELDS` says "name") and left the promise unmet for the value the
screen displays.

**Round thirteen's test could not have caught it, and that is worth recording.**
`test_every_field_the_overview_promises_actually_matches` samples a job name out of
the demo history — and every demo workload has a name the fold leaves alone:

```
node-evaluation          fold=node-evaluation          distinct=1 total=1   label!=name: False
midtrain                 fold=midtrain                 distinct=1 total=14  label!=name: False
cot-exp                  fold=cot-exp                  distinct=1 total=20  label!=name: False
ddp-pretrain             fold=ddp-pretrain             distinct=1 total=1   label!=name: False
att-speed-#              fold=att-speed-#              distinct=7 total=7   label!=name: False
tokenize-shards          fold=tokenize-shards          distinct=1 total=4   label!=name: False
rc-tok-github_code       fold=rc-tok-github_code       distinct=1 total=10  label!=name: False
soup-merge               fold=soup-merge               distinct=1 total=1   label!=name: False
```

`label == name` for all eight, so the assertion held vacuously on the only
history it was ever run against. This suite's recurring failure mode, again.

Fixed by adding the group's distinct member job names to the haystack. **The raw
names rather than `label` itself, for a measured reason** — this runs on every
keystroke, and round thirteen recorded cost as its objection to widening this
haystack:

```
filter_groups (current)                    0.46 ms
+ g.label for all                          8.39 ms      <- label walks the group
+ distinct raw names set for all           0.93 ms
filter_groups after fix                    2.10 ms
groups whose displayed label finds nothing NOW: 0 of 879
```

`label` costs 18x the whole filter because it walks every member to find the newest
run. The name set is a superset of what `label` can return — every one of the 879
displayed labels matches, checked, 0 uncovered — for 2.10 ms across 879 groups and
13,126 jobs. It also answers round thirteen's objection on its own terms: that
objection was about folding in **ids, states and node lists**, a far larger string
per group than the one or two names a workload actually has, and those three
deliberately stay out.

Tests: `TestTheNameOnTheOverviewIsSearchable` in `tests/test_index.py`, six cases.
The premise is asserted rather than assumed (`name == "s#e#"` while
`label == "s1e20"`) precisely because that is how round thirteen's test passed
while the defect stood; then the displayed label finds its group, and every label
in a mixed demo-plus-fixture history is findable. Three controls: the fold itself
still matches (what a reader who has learned the `#` notation types); a miss is
still a miss; and — the one this change could plausibly have broken — job id,
state and node still return **nothing** on the overview, which is round thirteen's
entire finding and would have been silently reopened by a haystack widened with
whole `Job` records instead of their names. Reverting the fix fails the two
label cases and leaves all four controls passing.

### Also changed

`README.md` — the test badge moved 1994 -> 2004. Caught by
`test_the_test_badge_matches_the_suite`, not by me.

### Open — reported, not changed

**A. `patterns.py:287` — a cancellation is kept out of the numerator and left in
the denominator, so the overview calls a workload critical while the patterns
panel calls it a warning.** Reproduced on real data, not constructed:

```
name                     part       runs  fail  canc  comp   memfrac   judged
nemotron-api             test         16    12     4     0     0.750    1.000
  index severity for nemotron-api test = crit failure_rate= 1.0 total= 16
```

`Job.failed` correctly excludes `CANCELLED`, so no cancellation is counted as a
failure — that half is right. But `find_repeat_failures` divides by
`len(members)`, which includes them, while `index.GroupStats.failure_rate`
(`index.py:111`) divides by `completed + failed` and documents that choice as *"the
honest denominator"*, on the reasoning that a deliberate kill and an abandoned run
are indistinguishable in accounting. Both numbers grade the same workload:
`severity` paints its overview row red at `>= 0.5` (`report.py:637`), and
`fraction > 0.8` at `patterns.py:368` sets the finding's severity. So the live
30-day report says, in one run:

```
  repeat-failure warning | 12 of 16 runs of nemotron-api in test failed; 11 were FAILED.
```

under a row the same run paints critical. It also decides an exit code:
`cli.py:1363` raises exit 1 only on a *critical pattern*, so a workload with no
successful run at all does not raise it if enough of its runs were cancelled.

Simulated over the whole 30-day history, switching this rule to the judged
denominator changes **nothing except that one severity** — no group starts firing,
none stops:

```
newly firing: []
no longer firing: []
severity changes: [(('nemotron-api', 'test'), 'WARNING', '->', 'CRITICAL')]
```

Not changed here because it moves a published severity and an exit code that a
caller may be keyed on, and because doing it properly means deciding whether the
evidence sentence should then name the cancellations it is no longer counting —
"12 of 16 runs failed", marked critical, is not a sentence a reader can derive the
severity from. `failure_rate`'s docstring already accepts that trade for the
overview ("NOT comparable to the RUNS column ... reserved for sorting and
severity"), so the precedent for leaving the sentence alone exists; the decision is
the maintainer's.

**B. `patterns.py:361` — "Stop resubmitting" is said to workloads that were
submitted once.** *(FIXED in round eighty-one — the wording only; the counts and the
grouping are unchanged.)* Every element of a job array is its own record with its own
`JobID`, and `group_key` folds them into one workload, so array fan-out counts as
repetition. On the real history:

```
cpas_audit       part=test kind=gpu n=11 distinct_masters=1
   states: {'FAILED': 8, 'COMPLETED': 3}
   top masters: [('53410199', 11)]
   sample ids: ['53410199_1', '53410199_2', '53410199_3', ...]
```

reported as `8 of 11 runs of cpas_audit in test failed; 8 were FAILED.` ->
`Stop resubmitting; the failure is deterministic. Reproduce interactively.` One
`sbatch --array`, one submission, and three of the eleven tasks completed — so the
failure is not deterministic either. `cpas_tQ` is the same shape at 6 tasks over 3
masters.

This is not a grouping bug and must not be fixed by exempting arrays: an earlier
round examined exactly that question for the memory rule, found that siblings have
always been evidence, and left it deliberately
(`TestArraySiblingsAlreadyCountAsEvidence`). Each element really is an allocation
that ran and burned resource, and "N of M runs" is honest about them. What has
drifted is the **action text**, which assumes M submissions. Left open because the
fix is a wording change on a surface that `render` shares, and because it needs the
master-id count — available, `job_id.split("_")[0]` — threaded into the evidence to
say the true thing instead.

**C. `patterns.py:113` — `newest_name`'s docstring describes a tie-break
`build_groups` does not have.** *(FIXED in round eighty-one — the docstring was the
wrong half, as this entry said.)* It says a group's members are ordered "start,
falling back to submit — with `numeric_job_id` breaking the tie";
`index.py:198` is `members.sort(key=lambda j: _stamp(j), reverse=True)`, with no
second key. Ties are the ordinary case for an array, whose tasks share a Submit.
Harmless today: `workload_label` deliberately calls `newest_name` rather than
indexing `jobs[0]`, and nothing in `src/` indexes `GroupStats.jobs[0]` (checked).
A documentation defect, not a behaviour one, and the docstring is the half that is
wrong.

**D. `patterns.py:543` — `find_memory_search` is the only one of the three
detectors with no report cap.** `find_repeat_failures` and `find_requeues` both
take `limit=REPEAT_REPORT_LIMIT` and summarise the tail; this one emits one finding
per qualifying group, unbounded. Two on the real 30-day history, so nothing to see
here yet, but the same 90-day window that produced the `_mem_walk` elision is what
this would need checking against.

### What else was looked at and found sound

* **A workload of one or two runs cannot trip any of the three rules.**
  `find_repeat_failures` needs `min_runs` *failures* as well as members (5),
  `find_requeues` needs 3 members with a closed earlier attempt, `find_memory_search`
  needs 3 OOMs. Verified against real data: the three requeue candidates on
  midway3 — `caai-sa6-li`, `caai-textstore`, `amd_reserve`, each with 2 requeued
  members — are all correctly silent, and `find_requeues(jobs)` returns `[]` over
  the whole 30 days.
* **Requeues are not double-counted.** `find_repeat_failures` and `find_memory_search`
  count only the surviving incarnation; `job.earlier` is read by `find_requeues`
  alone, and only for attempts that carry an End. Job 53274279 (`amd_reserve`) has
  two earlier incarnations, one still `RUNNING` with no End, and the open one is
  correctly dropped.
* **Het components would count as separate runs, and `numeric_job_id` ties them**
  — `numeric_job_id` on `123+0` and `123+1` both give `(123, -1)`, because it splits
  on `+` and keeps the head. Harmless as written: `sort` is stable and sacct returns
  components in order, so the submission order `find_memory_search` needs survives.
  Untestable against data here — this cluster's 30 days hold zero het jobs.
* **Names that collide across partitions group separately, correctly.** Nine on the
  real history, e.g. `software` at 167 runs in `test` and 14 in `beagle3`, and
  `vshrink` in `test` and `caslake`. `group_key` is
  `(fold, partition, kind, user)`, so each is its own workload and its own row.
* **`-n/--limit` changes no aggregate.** Checked across `--json`, the default view,
  `--overview`, `--nodes` and `--sizing` at several limits: every figure in
  `summary` is identical except `findings_jobs_shown`, which is what it is for, and
  the only other differences are the truncation notes that announce themselves
  ("… 4 more workloads (22 runs) holding 7.0% of the compute") and one grey caption
  that stops explaining `#` when no shown row contains one.
* **Sort ties are deterministic.** All six `_SORT_KEYS` can tie — `rate` and
  `runs` do so on the real history — and `sorted` is stable, including under
  `reverse=True`, so ties resolve to `build_groups`' cost order and the same query
  gives the same screen every time. The keys are *not* total orders and permuting
  the input reorders equal rows; that is not reachable, because the only caller
  passes `History.groups`.

## Round thirty-eight — a dumb terminal that got colour, a closed pipe that exited 120, and the tests those two fixes should have shipped with

Two defects, both found by comparing this tool against its four siblings rather
than against a cluster: the question asked each time was "does slurmpast answer
this the way nodetop, rapidu, slurmate and slurmwatch answer it, and if not, which
one is right?" 1987 tests before, **1994** here; all four gates clean.

Recorded late, and that is part of the finding. Both fixes were made in an earlier
pass of the same session and landed **without tests**, which this file's own
Development rule forbids -- "a fix ships with a test and its control". The code was
correct; the round was not. The tests below were written afterwards and verified by
reverting each fix, which is the only way to know a test has teeth.

### Fixed

**1. `report.py:238` — `TERM=dumb` got colour, and this was the only tool in the
family that did.** `Style.__init__` decided colour with
`hasattr(stream, "isatty") and stream.isatty() and not os.environ.get("NO_COLOR")`.
`TERM=dumb` is a terminal that cannot render escape sequences and *is* a tty, so
`isatty()` answered "colour" for it. An Emacs shell buffer, a CI log and a serial
console all set it.

Measured before the fix, under a real pty so colour was on at all:

```
  TERM=xterm-256color                colour SGR = 7
  TERM=dumb                          colour SGR = 7      <-- should be 0
  TERM=xterm-256color NO_COLOR=1     colour SGR = 0
```

rapidu and slurmate already pair the two checks, and rapidu's `ui` module names
both `NO_COLOR` and `TERM=dumb` in its docstring -- so the family standard existed
and this tool was outside it. Fixed by adding `os.environ.get("TERM", "") != "dumb"`
to the same condition. `--no-color`/`enabled=` still override, in both directions.

Tests: `TestADumbTerminalGetsNoColour` in `tests/test_portability.py`, four cases --
the `dumb` case, a control asserting a real terminal *still* gets colour (a test
that only checked `dumb` would also pass if colour were switched off everywhere),
`NO_COLOR` independently, and the explicit-flag override.

**2. `cli.py:908` — `slurmpast --json | head` printed a BrokenPipeError after its
output and exited 120.** No SIGPIPE handling existed. Python ignores SIGPIPE, so the
write raised, and CPython's shutdown flush of a closed stdout printed:

```
Exception ignored in: <_io.TextIOWrapper name='<stdout>' mode='w' encoding='utf-8'>
BrokenPipeError: [Errno 32] Broken pipe
```

on **stderr** -- so a caller redirecting only stdout still saw it -- then exited
**120**, which is neither a shell convention nor a decision; it is the interpreter
failing to flush. `slurmpast --json | jq` and `--plain | head` are how a long report
actually gets read.

The other three tools had all already settled this and disagreed only on the code:
nodetop restores the default disposition (exit 141, the Unix filter convention),
rapidu and slurmwatch catch `BrokenPipeError` and exit 0 -- and slurmwatch's
`cli.py` comment names this exact failure, "exited 120 with 'Exception ignored ...
BrokenPipeError' on stderr instead of 0". slurmpast was the one with nothing.

Fixed by restoring `SIGPIPE` to `SIG_DFL` at the top of `main()`, beside the
existing `KeyboardInterrupt` -> 130 wrapper, whose docstring already reasons about
shell exit-code conventions. Now: stderr empty, exit 141. Normal runs unaffected.

Tests: `TestAClosedPipeIsNotAnError`, three cases -- the disposition is `SIG_DFL`
by the time `_main` runs; a control that checks in a *fresh interpreter* that
Python's own default is `SIG_IGN`, so the fix changes something real and this
test's own signal handling cannot supply the answer; and an end-to-end case
asserting no "Exception ignored" or "BrokenPipeError" reaches stderr when stdout
closes early.

Reverting both fixes fails exactly the three behaviour assertions and leaves all
four controls passing, which is what a control is for.

### Also changed

`README.md` — the test badge moved 1987 -> 1994. Caught by
`test_the_test_badge_matches_the_suite`, not by me.

### Nothing withdrawn

### What else was looked at and found sound

The same cross-family comparison was run over every duplicated rule and adjudicated
against an authority where one exists. None of it produced a defect, and the list is
recorded so a later round does not redo it:

* **Duration parsing** vs nodetop's. The two disagree on six inputs -- `1-00:30` is
  86430 s here and 88200 s there -- and **both are right**: Slurm has two duration
  grammars, and `parse_duration`'s docstring correctly scopes this one to accounting
  output (`[DD-[HH:]]MM:SS`, bare = seconds) while nodetop implements `sbatch --time`
  (bare = minutes). Applying the sbatch rule to this function would be the bug.
* **Memory parsing** vs slurmwatch's and slurmate's. All three agree on every real
  value. The bare-integer divergence recorded in `parse_mem_limit`'s docstring is
  fixed in both other tools.
* **`expand_nodelist`** vs `scontrol show hostnames`: agrees on 15 specs including
  mismatched-width ranges. `width = len(low)` is the correct Slurm rule -- nodetop
  had `max(len(lo), len(hi))` and was wrong; fixed there, not here.
* **Diagnosis codes** vs raw sacct over 932 jobs / 30 days: `host-oom` is *exactly*
  the `OUT_OF_MEMORY` set (104, zero discrepancy either way), `cancelled` exactly
  `CANCELLED` (217), and `timeout-real`/`timeout-hang` a zero-overlap partition of
  `TIMEOUT` (67 + 54 = 121) whose split tracks CPU evidence -- median utilisation
  0.0001 against 0.0062.
* **Slurm filename patterns** (`logs.expand_pattern`): the code set
  `{%, A, a, J, j, N, n, s, t, u, x}` is exactly sbatch's documented set; `%4j` on
  job 128 gives `0128`; the het-component and array cases resolve via `JobIDRaw`;
  and `--output=o-%2000000000j.out` is capped at `MAX_PAD_WIDTH` rather than
  building a 2 GB string.
* **Determinism**: `--demo --json`, `--overview` and `--sizing` are byte-identical
  across runs.
* **`TERM=dumb` and `NO_COLOR`** now verified for all five tools; `--ascii` emits
  zero non-ASCII bytes in all five.

## Round thirty-five — one workload, two names, and a suite that could not run

Five defects, found by running the working tree against **two** new clusters in
parallel while re-checking a third after every change. The instruction that shaped
the round was "don't fix one thing while breaking the others", so midway3 was
re-run at each step rather than at the end.

| | midway3 | Mercury | Pythia |
|---|---|---|---|
| OS | RHEL 8 | RHEL 9.7 (Plow) | RHEL 8.10 (Ootpa) |
| Slurm | **20.11.8** | **25.11.3** | **24.11.5** |
| Python | 3.11.14 (conda) | 3.13.15 (venv) | 3.12.14 (venv) |
| `JobAcctGatherType` | `jobacct_gather/linux` | `jobacct_gather/cgroup` | `jobacct_gather/cgroup` |
| `JobAcctGatherFrequency` | 30 | 30 | 30 |

Mercury and Pythia share one NFS home (same inode for `/home/youzhi`), so one
rsync served both, but they are different OS images with different interpreters and
two Slurm minors apart. Data: 26 of the caller's own jobs on Mercury, and 2,044
jobs in 280 workloads over two days `--all-users` on Pythia. Every finding below
was reproduced by running the tool, and each has a test that fails without the fix
-- verified by reverting the fix and watching the test fail, which caught two
assertions that passed either way (§2 and §4).

### 1. The suite could not run on either new cluster

```
$ python3.12 -m venv ~/spv && ~/spv/bin/pip install -e ".[dev]"
$ ~/spv/bin/python -m pytest -q
FAILED tests/test_audit.py::TestTheSdistShipsASuiteThatCanRun::test_the_built_sdist_carries_every_file_under_tests
FAILED tests/test_audit.py::TestTheSdistShipsASuiteThatCanRun::test_the_built_sdist_carries_what_the_repo_audits_read
E   build._exceptions.BuildBackendException: Backend 'setuptools.build_meta' is not available.
2 failed, 1821 passed
```

Identical on Mercury (3.13.15) and Pythia (3.12.14). `_built_sdist` calls
`ProjectBuilder(...).build("sdist", ...)`, which runs the backend **in the current
interpreter** rather than fetching it into an isolated environment -- and since
Python 3.12, `venv` no longer seeds `setuptools`. `build` was in `[dev]`; the
backend it needs was not.

The class this sits in exists precisely because "the way its portability claims get
checked is somebody on another cluster downloading the *released* artefact and
running it there". On the two clusters that describes, it failed.

midway3 passed 1823 for an unrelated reason: its conda env happens to ship
`setuptools` 81.0.0. A local gate runs on one interpreter and could not see this,
which is the same shape as the `tomllib` finding at §*Round twelve*.

Nor could CI, and that is worth stating rather than leaving implied: `ci.yml` has an
`Install build deps` step that pip-installs `"setuptools>=77" wheel` *before*
`pip install -e ".[dev]"`, so the gate has always had a backend by hand. The
dependency was therefore satisfied in the two environments that run the suite
routinely and declared in neither -- which is why the first environment to install
the package the way its own README describes was the first to fail. The fix moves
the guarantee from CI's shell into the manifest, where anyone installing the test
extra gets it; the CI step is now redundant rather than load-bearing, and is left
in place because a workflow that installs its own build deps costs nothing.

**Fixed** in `pyproject.toml`: `setuptools>=77` and `wheel` -- the two names already
in `[build-system] requires` -- added to `[dev]`, since the suite performs an
in-process PEP 517 build. `tests/test_audit.py` additionally converts a missing
backend into a skip that names the fix, so someone running bare `pytest` gets a
sentence instead of a 40-line build traceback about an sdist that is fine.

Two tests, and the second is the control on *which* backend: `[build-system]
requires` must be a subset of what `[dev]` installs, so the pin cannot drift if the
project ever moves off setuptools.

### 2. One workload, named two ways in one report

The overview table and the cross-run finding below it disagreed about what the same
20 runs were called:

```
overview   m110_robustness_current_source_20260823_c9ea44  20 runs  0 completed  20 flagged
patterns   20 of 20 runs of m#_robustness_current_source_#_c#ea#e_v# in standard_hopper failed
```

`GroupStats.label` deliberately shows a group's one real job name instead of the
fold, on its own stated grounds: the `#` "hides the one name it is standing in for
and invents a family that does not exist". The findings in `patterns.py` named their
groups `key[0]` -- the raw fold -- at four sites (`patterns.py:253`, `:421`, `:535`,
`:539`), so the rule reached the table and `--nodes` and stopped there.

**Fixed** by extracting the rule into `patterns.workload_label(signature, jobs)` and
routing both surfaces through it; `GroupStats.label` now delegates, so there is one
copy. This is the "one place" that property's docstring already claimed for it.

Why the existing tests did not catch it: the suite had tests for the table's half of
this rule and they passed throughout, because their fixtures are named `cot-exp` and
`rc-tok-github_code` -- **no digits, so the fold is the identity**, and a surface
printing the fold is indistinguishable from one printing the name. Every name in the
new tests carries digits.

The first version of the cross-surface test asserted over `render_overview` alone
and passed with the defect still in place -- `render_overview` draws only the table,
and the cross-run section is `render_patterns`, which the CLI composes separately.
Corrected to render both.

### 3. A log sent to `/dev/null`, reported as moved or deleted

```
$ slurmpast 182712 --plain          # Pythia, a real DEADLINE job
job 182712  DEADLINE
  log none at /dev/null — moved or deleted; --log-dir points at it
```

`/dev/null` is a character device, so `os.path.isfile` is False for it, and
`probe_path`'s last line folded "exists but is not a regular file" into `absent`:

```python
return "found" if os.path.isfile(path) else "absent"  # logs.py:320
```

So the single most common way to say "I do not want this output" was reported as a
log that had gone missing, with `--log-dir points at it` offering a recovery for a
file that was never written. **152 of 2,675 records on Pythia over three days --
5.7%, and the fourth most common log path on the cluster.**

That is the same error this function was written to stop making one branch up: a
stat that *succeeded* is not a stat that found a file, just as a stat that failed is
not a stat that found nothing.

**Fixed**: `probe_path` gains `discarded` (the null device, decided by intent before
the stat, so a site where `/dev/null` is unstattable is still not told its log
moved) and `special` (present, not a regular file -- a directory, a fifo, another
device). Both get their own sentence. `--json`'s `log_expected.status` can therefore
now carry two values it could not before; see *Consequence for the numbers*.

### 4. The dashboard and `--plain` disagreed about a missed log

`--plain` had grown four spellings keyed on `probe_path` -- naming the recorded path,
and distinguishing absent from unreadable from unknown. The dashboard printed one
unconditional line:

```python
body.append("  log  none found — --log-dir points at one\n", ...)  # tui.py:1837
```

on a comment claiming "the path is unknowable". That stopped being true when Slurm
24.05 began recording `StdOut`, which is exactly the version range both new clusters
sit in -- so on a 24.11 cluster the two front ends described the same job
differently, and nothing on either screen could show a reader that, because only one
of the two is ever in front of them.

**Fixed** by moving the wording to `render.log_miss_detail(job)` and calling it from
both, which is what `render.py` is for. The `--no-logs` guard stays with each caller,
because every spelling is a claim about the filesystem.

Its source-inspection control also had to be fixed twice: anchored on a trailing
quote it matched neither version, and without the quote it matched the explanatory
comment above the fixed line. It now walks the string literals with `ast`, since only
a literal can reach the screen.

### 5. `--failed` was named as the reason a window was empty; `--partition` was not

```
$ slurmpast -p nonexistent_xyz -S now-30days --plain      # Mercury, 18 jobs in the window
slurmpast: no jobs for youzhi since now-30days
```

A partition name is the one argument that reliably does not survive being carried
between clusters -- midway3 has `caslake`, Mercury `standard`, Pythia
`standard_hopper` -- so `-p` naming something this site has never heard of is the
ordinary way to reach that message, and it stated something false about the window.
`--failed` was already named there; `-p` and `-E` were not.

**Fixed** in `cli.py`: every narrowing filter is named, and `--until` is reported
when given, so the window is not described by half. With no filter the sentence is
unchanged -- that is the control.

### Checked, and not defects

* **A 101-run workload showing zero completed and zero flagged.** Row 15 on Pythia,
  `full-data-supervised-#-#_#-#`. All 101 are `CANCELLED by 89161`, and a
  cancellation is deliberately neither a success nor a failure -- the behaviour
  §*Round nine* settled and a test pins. Correct as shown.
* **`--all-users --nodes` exiting 2 on midway3.** `sacct did not answer within 300s
  — ... Narrow the window with -S, or raise SLURMPAST_TIMEOUT`. midway3 holds
  ~938,576 job ids in seven days; the timeout is real and the message says what to
  do. Both new clusters answer the same query in seconds.
* **Exit 2 for every own-jobs view on Pythia.** The caller genuinely has no jobs
  there (`sacct -X -u youzhi` returns nothing), and `no jobs for youzhi since
  now-7days` is the right answer. `--all-users` worked throughout, which is how the
  rest of the round got its data.
* **The clipboard file at mode 0700 rather than 0600.** Booth's NFS home forces
  0700 on every file regardless of the mode requested -- a probe creating a file at
  `0o666` also read back `0o700`, and `fchmod` did not move it. The security intent
  (no group or other access) holds, and it fails *more* restrictive, so this is a
  filesystem ACL policy rather than a defect. The tests assert exact 0600 under
  pytest's `tmp_path`, which is local, and are right to.

### What was exercised

Every text surface on all three clusters (overview, `--overview`, `--patterns`,
`--nodes` with both metrics and `--all-workloads`, `--sizing`, `--failed`, `--json`,
`--ascii`, `--no-color`, all six `--sort` modes, `--no-logs`, `-n 0`, `--strict`,
`--demo`, empty and inverted windows, a nonexistent partition), per-job surfaces over
a spread of states on both new clusters (post-mortem, `--steps`, `--json`, `--ascii`,
`--strict` across 12 jobs; every JSON payload parsed), and the dashboard driven by
keystroke on both: workload drill-down, job detail, `--nodes` with metric and control
toggles, patterns, search, all sort and filter cycles, copy, and the clipboard file
confirmed discarded on exit. No traceback on any surface on any cluster.

---

## Round thirty-four — a stranger's job, folded in as your own requeue

Three defects, on the third cluster this package has been run against and the
first that is neither Midway. Mercury, at the University of Chicago Booth School
of Business: RHEL 9.8 (Plow), kernel 5.14, **Slurm 25.11.3**, cgroup v2,
`JobAcctGatherType = jobacct_gather/cgroup`, `sacct --helpformat` advertising 120
fields, system `python3` at 3.9.25. Run against 84,932 real jobs in 2,258
workloads over fourteen days, `--all-users`, not fixtures.

Two things about the environment are worth recording before the defects, because
both were checked and neither is one:

* **Field negotiation held at the newest Slurm yet.** The tool asked for 83 of the
  120 fields and every one of them exists here; stderr was empty on every
  invocation. Midway3 is 20.11.8 and midway2 is 23.02, so 25.11.3 is a five-year
  span across three clusters with no field drift.
* **The `--state` + relative `-S` quirk this file documents at `sacct.py:22`
  reproduces exactly.** `sacct -S now-2days --state=COMPLETED` returns 0 rows here
  while 23,212 such jobs exist; adding `-E now` returns 23,213. The workaround
  already in place handles it.

The Python floor also behaves: `pip install slurmpast` under the system 3.9
refuses cleanly and installs nothing.

### 1. `sacct -D -j <id>` has no window, so it answers with jobs that are not yours

`slurmpast <jobid>` reported a requeue that never happened on **40 of the 40** ids
sampled from three recent days:

```
$ slurmpast 509531
job 509531  COMPLETED
    requeued         1x · COMPLETED after 00:01:09
```

The two rows sacct returns under `-D` are not two incarnations of one job:

```
$ sacct -D -j 509531 -X -P -o JobID,Cluster,User,Account,Partition,JobName,Submit,End,State,NodeList
509531|mercury|aranda   |pi-vgupta4|standard|dsa-3-20                          |2019-03-03T18:35:08|...|mcn36
509531|mercury|cmbrennan|phd       |highmem |did_bigquery_priority_general_2026|2026-08-19T22:21:07|...|mcn58
```

Same cluster, but a different user, account, partition, job name and node, seven
years apart. Slurm's job-id counter wrapped and this slurmdbd still holds the 2019
records. `_fold_incarnations` grouped on `job_id` alone, so it filed a stranger's
job as the reader's own earlier attempt and printed it as requeue history — on
every per-job view on the cluster.

**Scope, measured rather than assumed.** Windowed queries are clean: a `-S
now-7days -E now` sweep returns 59,860 rows under `-D` against 59,849 without, and
**zero** rows with a pre-window `Submit`. So `--overview`, `--patterns`, `--nodes`
and `--sizing` were never affected. The per-job path is hit because it queries by
id with no window, and **passing `-S` does not suppress it** — there is no window
on that query to pass, so there was no user-side workaround.

**The fix is identity, not time.** `_same_job` compares cluster, then uid, then
user, and the fold keeps only the trailing run that still matches the newest row.
A requeue cannot change whose job it is — Slurm re-queues the same submission, so
those fields survive it — whereas a recycled id is a different submission by
whoever drew the number next.

A gap threshold was the obvious alternative and is worse. The normal requeue shape
*is* "the previous attempt ended before this one was submitted", so the sign of
the gap carries no signal at all, and any cutoff would eventually reject a job
that sat requeued and held. Missing data defers rather than splits: sacct leaves
these fields blank often enough that a blank must not break a requeue that really
happened.

The one-Job-per-id contract is kept deliberately. `logs.py:727` and `cli.py:439`
both key log resolution on `job_id`, so emitting two Jobs for a recycled id would
hand one of them the other's log. The foreign rows are dropped from `earlier`
instead. The consequence worth stating: a window wide enough to contain both jobs
still reports one of them, which is what the fold did before this round and is not
made worse by it.

Verified on the cluster, with the control that matters — job 504187, a genuine
same-user requeue on the same cluster, still reports `requeued 1x · REQUEUED
after 20.0s`.

### 2. The `memory-slack` caveat was written for the other gatherer

One run of the tool printed both of these about the same number:

```
--sizing:  MaxRSS comes from the cgroup peak here (jobacct_gather/cgroup), so it is
           the step's real high-water mark rather than a sum over processes.
per-job:   Try --mem=25G (peak plus ~30%). MaxRSS over-reports multi-process jobs,
           so treat it as an upper bound.
```

The second is false here. `site.maxrss_caveat()` exists so this sentence is asked
of the cluster rather than assumed, and returns `rss_from_cgroup: True` on this
one. `diagnose.py` already called it for `host-oom` and `rss-above-limit`, the two
findings immediately above — `memory-slack` was the single site that was missed,
which is why this reads as an oversight rather than a decision.

Fixed by routing it through `maxrss_caveat()` like its neighbours. The pasteable
`--mem=25G` spelling from `format_mem_flag` is pinned by a test so the rewording
cannot quietly take it back to `--mem=25.0 GiB`.

### 3. `format_bytes` fell from MiB straight to raw bytes

Both of these were on one screen:

```
    read             9.5 GiB          rate  488928 B/s sustained
    509531.batch     ...  79.0 MiB    612794 B
```

The two figures a reader most wants to compare, in a column, in units that cannot
be compared by eye. A `KiB` tier was added between MiB and the byte floor. Bytes
remain below 1 KiB, where they are the honest unit and where `format_bytes(0)`
must keep rendering `0 B` — a test already pinned that and still does.

Documented as "GiB/MiB string", so this was semi-deliberate rather than an
accident; nothing but the zero case was pinned by a test, and the docstring now
says why the tier is there.

### What changes for a user

`slurmpast <jobid>` stops reporting a requeue on any cluster that has recycled job
ids, and keeps reporting one where the incarnations are genuinely the same job.
The `memory-slack` action now says what MaxRSS means *on the cluster it is running
on*, so on a `jobacct_gather/cgroup` site it no longer contradicts `--sizing`; on
a `jobacct_gather/linux` site the wording is unchanged. Any figure between 1 KiB
and 1 MiB — `io_rate` most often, and small step writes — renders as KiB where it
rendered as a raw byte count, so anything grepping plain output for a bare `B`
should match the `--json` field instead, which is untouched.


## Round thirty-three — four defects a second cluster found in a day, and twenty-one more the rounds after it

The first round driven entirely by someone else's report. slurmpast 0.7.0 was
installed from PyPI onto **midway2** -- CentOS 7.9, glibc 2.17, Python 3.14.6,
**Slurm 23.02.0**, cgroup v1, a one-node free partition and no GPU -- and
exercised against that cluster's real accounting history. Every axis of that
environment differs from the Midway3 the tool was written on, which is the whole
point: none of the twenty-five below is midway2-specific, and none of them was reachable
from this repository's fixtures. The last two were not in
`slurmpast.md`. One was found by verifying the other four the way that report's
author verifies things, against the artefact PyPI actually serves; the other was
filed against this tool inside *another* package's report, where it would have
been easy never to read.

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A field containing a newline shattered the record, so 41 real rows parsed as 56 "jobs" -- 45 of them shell fragments -- and the overview reported 47 unterminated records where there were 2 | `sacct.py` | `TestAFieldMayContainANewline` |
| 2 | `slurmpast > report.txt` launched the dashboard anyway: 26 KB of escape sequences into the file, then a wait for a keypress a redirect cannot deliver | `cli.py` | `TestARedirectMustNotLaunchTheDashboard` |
| 3 | The internal grouping signature was printed as the workload's name, so an all-digit job name read as `#` and a date-stamped one as `#-#` | `index.py`, `nodes.py`, `patterns.py` | `TestADateStampedWorkloadIsNamedNotFolded`, `TestTheFoldIsOnlyShownWhenItStandsForSomething` |
| 4 | `--nodes` printed "2 nodes below threshold omitted" directly above "there is nothing to attribute to a node" | `render.py` | `TestTheBaselineDoesNotContradictTheEmptyReason` |
| 5 | The released sdist shipped 18 of the 20 files in `tests/`, so the suite it carried could not be collected at all -- later filed independently as SP-9 | `MANIFEST.in` (absent) | `TestTheSdistShipsASuiteThatCanRun` |
| 6 | A unit-less memory limit was read as bytes, where Slurm means mebibytes -- `ReqMem=16` as 16 bytes rather than 16 MiB | `duration.py`, `sacct.py:701` | `TestAUnitLessMemoryLimitIsMegabytes` |
| 7 | `sacct -D` was never passed, so a job requeued on NODE_FAIL or preemption showed only its last attempt -- 27m49s on a failed node, invisible | `sacct.py`, `model.py`, `render.py`, `cli.py` | `TestARequeuedJobIsNotInvisible` |
| 8 | Asking for two report sections printed one and said nothing, the winner decided by branch order; `--steps` without a job id was a silent no-op | `cli.py` | `TestTwoSectionsAreBothPrinted`, `TestJsonTakesOneSectionAtATime`, `TestStepsNeedsAJobToStep` |
| 9 | `SLURMPAST_TIMEOUT` accepted `garbage`, `0` and `-5` and silently used the default -- the package's whole environment surface, untested | `sacct.py` | `TestTheOnlyEnvironmentVariableIsValidated` |
| 10 | A sub-second timeout was reported as "did not answer within 0s", which reads as the tool's own zero rather than the caller's budget | `sacct.py:321` | `TestASubSecondTimeoutSaysWhatItWas` |
| 11 | A log matched by timing let the tool report a *critical* GPU OOM for a job that allocated no GPU | `diagnose.py` | `TestAMisMatchedLogCannotInventAGpuCause` |
| 12 | With both streams present it ranked the empty `--output` first and then said no log explained the failure | `logs.py` | `TestTheFailurePostMortemPrefersStderr` |
| 13 | A failed job whose log matched no rule read "nothing to flag" -- exposed by fixing 12 | `diagnose.py` | `test_a_failure_with_an_unrecognised_log_is_still_flagged` |
| 14 | `scontrol` knows the log path on every Slurm and was never asked, so the guess ran even when the truth was available | `sacct.py`, `cli.py` | covered by 11-13's fixtures; the lookup itself is verified against a live job |
| 15 | The NCCL rule fired for a job with no GPU and no peer rank, and `cuda-oom`'s new guard was looser than the one its neighbour uses | `diagnose.py` | `TestACollectiveFaultNeedsADeviceAndAPeer` |
| 16 | Nothing pinned that a `%j` name match beats a timing decoy -- the precondition the reporter's own narrowing rests on | `logs.py` (behaviour) | `TestANameMatchBeatsATimingDecoy` |
| 17 | `TotalCPU` misses work in reparented process trees, and the CPU finding and `--sizing` advice both presented a lower bound as fact -- telling a job using its 8 cores to ask for 1 | `site.py`, `sizing.py`, `diagnose.py` | `TestTheCpuFigureCarriesItsOwnLimits` |
| 18 | `--sizing` emitted `#SBATCH --cpus-per-task=34` for a partition whose nodes have 28, on a workload with 401 runs -- every job submitted with it is refused | `site.py`, `sizing.py`, `report.py` | `TestAnUpwardAdviceCannotExceedTheNode` |
| 19 | Under a valid non-UTF-8 locale four of five text modes exited 1 with **zero bytes**; one job name outside the encoding took down every mode for every user | `cli.py` | `TestANonUtf8StdoutStillProducesOutput` |
| 20 | `sbatch --export=NONE` left no identity and `--plain`/`--json`/`--overview` raised an unhandled `OSError`, while the TUI handled it | `sacct.py`, `cli.py` | `TestTheUserIsResolvableWithoutAnEnvironment` |
| 21 | `--sizing` rendered "no data" as a green all-clear and silently dropped every workload it could not judge | `report.py` | `TestNoDataIsNotAnAllClear` |
| 22 | `-n` clipped `--json`'s findings array with nothing in the payload recording it, and `-n 0` was a usage error where a sibling tool spells it "unlimited" | `cli.py`, `report.py`, `index.py` | `TestTheJsonSaysHowMuchItClipped`, `TestZeroMeansUnlimited` |
| 23 | The scan mode exited 0 while reporting critical findings, and the 0/1/2 contract with its mode-dependent `1` was undocumented | `cli.py` | `TestTheExitCodeContractIsStatedAndOptional` |
| 24 | A log behind a mode-700 home was reported "moved or deleted" -- wrong for 104 of 106 foreign jobs on the reporting cluster -- and `--json` collapsed every miss to `null` | `logs.py`, `report.py`, `cli.py` | `TestAnUnreadableLogIsNotReportedAsDeleted` |
| 25 | A 100% baseline makes the node comparison impossible, and the screen blamed sample size and prescribed a wider window that cannot help | `render.py` | `TestADegenerateBaselineIsNamedRatherThanBlamedOnSampleSize` |

### 1. `sacct --parsable2` does not escape a newline inside a value

`--parsable2` separates fields with the delimiter and records with a newline, and
it escapes neither. Several of the 85 fields this tool asks for legitimately hold
a newline: `SubmitLine` is the common one, because `sbatch --wrap=$'echo one\necho
two'` records the whole multi-line script, and `Comment`, `AdminComment` and
`WorkDir` can carry one too. Slurm has stored `SubmitLine` since 21.08, so the
trigger is the *submit style* and not the site.

Splitting on newlines therefore promoted every continuation line to a record.
Measured on midway2 against a real 60-day history:

```
raw lines:            123
lines with delimiter:  41      <- the real record count
records parsed:        56      <- 15 too many, and 45 of them junk
records with a NON-NUMERIC job id: 45
```

```
job_id='hostname; cat /etc/redhat-release; ldd --version | head -1'
job_id='module use /project/rcc/youzhi/modulefiles'
```

None of the 45 carries an `End`, so each was `open_ended`, and the overview said:

```
  9 jobs in 8 workloads · 77.8% completed
  47 unterminated, excluded          <- the true number is 2
```

`45 phantoms + 2 real`. The one line whose entire purpose is explaining why the
job count is lower than expected was manufacturing the discrepancy it explained.

Records are now reassembled: a physical line opens a new record only when it
carries the delimiter *and* the text before the first one is shaped like a JobID;
anything else continues the record above it, newline included.

**Counting delimiters -- the fix the report suggested -- was tried first and is
wrong in the case that matters.** `SubmitLine` is the *last* field in the query,
so the first physical line of a shattered record already holds every delimiter a
complete one has. A rule that closes on the count closes there, and silently
truncates the script at its first newline: the phantom records disappear, every
count comes out right, and the job screen quietly loses most of the submit line.
`test_the_multi_line_submit_line_survives_whole` is the test that separates the
two, and it is why the boundary test does not depend on where the field sits.

The JobID guard is deliberately loose -- first character a digit, no whitespace --
rather than the anchored `^\d+(_\d+)?(\.\S+)?$` the report proposed. Every JobID
Slurm emits has both properties (`123_[1-20%10]`, `123+0`, `123_4.batch`), while
nothing else about the spelling is guaranteed across releases, and on a package
whose point is running on a cluster nobody here has seen, discarding a real row is
a worse failure than admitting a malformed one.

That is not a hypothetical. Run against Midway3's real 30-day history -- 43,913
accounting lines, 13,387 records -- the anchored spelling rejects exactly two
rows, and both are real:

```
'53421602_[10-15%5]' | cloze_S | CANCELLED by 940740146
'53488568_[1-6%1]'   | n93big  | CANCELLED by 940740146
```

A pending array range is written `<id>_[lo-hi%throttle]`, which the anchored form
has no branch for. Taking the report's regex literally would have fixed a parser
that invented jobs by shipping one that deletes them.

The same run is the reason this bug could not have been found here: every one of
those 43,913 physical lines carries the delimiter, so nothing on this cluster's
history is multi-line at all. The fix is a no-op on Midway3 and load-bearing on
Midway2, which is the whole argument for the second cluster.

**Narrowed from the report, then reversed by its author's reply.** It also asked
that rejected records be *counted* rather than silently dropped. They were not, on
the reasoning below -- and the reporter's feedback answered it: `--json` is a
channel that already exists and carries the number without touching `parse`'s
contract. That was right, so the count ships: `parse` fills an optional `stats`
dict, `Sacct` holds it, and `--json` emits `dropped_rows` only when non-zero, so a
well-formed payload is byte-identical.

Two things went wrong in the first attempt at it, both caught by probing rather
than reading. A second counter for "first field is not a JobID" cannot fire --
`_records` only opens a record on a JobID-shaped head, and JobID is field 0, so the
in-`parse` test re-asks a settled question -- and shipping one that permanently
reads 0 would read as evidence of soundness. And the justification was wrong too:
a line whose head is not JobID-shaped becomes a *continuation*, not a discard. What
is actually counted is the pipe-shifted row, reachable on the `|` fallback used by
any sacct older than 17.11. `TestARefusedRowIsCounted`.

The original reasoning, kept because the decision stood for several rounds: There is no channel from `parse` to
the screens for such a count, and adding one touches `sacct` → `cli`/`tui` →
`History` → both front ends for a number that reads 0 on every well-formed
cluster. Dropping a row the parser cannot trust is the policy this module already
documents for a pipe-shifted row, and the harm the count was asked for -- garbage
silently binned into `open_ended` -- is gone either way. Recorded here rather than
quietly skipped.

### 2. There is no tty guard anywhere in the package

Measured on midway2 under a 20-second `SIGKILL` cap:

| command | rc | alt-screen | bytes written |
|---|---|---|---|
| `slurmpast -S now-2days > file` | **137** | yes | 26,514 |
| `slurmpast -S now-2days \| cat` | **137** | yes | 26,514 |
| `slurmpast -S now-2days --plain \| cat` | 0 | no | 2,157 |

So the most ordinary thing anyone does with a report -- redirect it to a file to
read later or attach to a ticket -- wrote 26 KB of ANSI into the file and then
hung until killed. Under cron or CI the job never finishes.

The package had exactly one `isatty` call, in `report.Style`, and it only chooses
colours. `main` now degrades to `--plain` when either stdin or stdout is not a
terminal. Both, because Textual reads keys from stdin: `slurmpast </dev/null`
paints a screen nobody can drive or quit.

Degrading rather than erroring, and silently. `--plain` carries the same
information, so a redirect should simply work; a note on stdout would corrupt the
file being written, and one on stderr would be noise in every CI log for a
fallback that did what was wanted. `--help` now says `--plain` is automatic when
stdout is not a terminal.

### 3. The grouping signature is not always a name

`normalize_name` folds digit runs so that reruns group -- `att-speed-23` and
`att-speed-40` are one workload -- and the folded key was then displayed as the
workload's name. A name that is *entirely* digits and separators folds to
placeholders and punctuation, which identifies nothing. On midway2's cluster-wide
window this was row 23 of the top 25:

```
  #   JOB NAME                        PARTITION  RUNS COMPLETED FLAGGED  CPU-HOURS
  23  #                               broadwl      20        14       6  559 / -
```

and on `--nodes`, in both the caption and the empty-table sentence:

```
  controlled for workload: only #-# counted (placement is not random)
  No hangs recorded for #-# in this window, so there is nothing to attribute to a node.
```

`--json` carried `"workload": "#-#"`, confirming the value and not a rendering
artifact. Date-stamping a run is one of the most common naming conventions there
is, so this is not an edge case.

Both surfaces now fall back to the most recent run's real `JobName` when the fold
kept no letter, from one rule in `patterns` so they cannot disagree -- the reason
`render.py` exists, applied to a rule rather than a renderable. `GroupStats.label`
already did exactly this for a group covering a single name; this is the second
branch of the same idea.

**The grouping is unchanged, and that is the load-bearing part.** `Workload.matches`
normalises before comparing, so the stratum `--nodes` controls on is identical
either way; `GroupStats.name` still holds the fold; `--json` still emits a name,
which is what its consumers read. Where the fold still says something -- `a#`,
`att-speed-#` -- it is kept, because substituting one arm's name there would claim
the screen controlled on less than it did. `test_one_surviving_letter_is_enough_to_keep_the_fold`
and `test_a_folded_name_that_still_says_something_keeps_its_fold` are the controls,
and both pass against the reverted tree.

**One claim in the report is narrowed rather than adopted.** It reasoned that the
`#` row "will collide with every other all-numeric job name on the cluster -- so
the row may not even be one workload". `group_key` is `(signature, partition,
kind, user)`, so a collision needs two all-numeric naming conventions from the
same person on the same partition. That is possible and no worse than the fold
this tool already accepts elsewhere; it is not the cluster-wide merge the sentence
describes, and the grouping was left alone on that basis.

**The reporter's reply then found the cost of leaving it alone, and it is real.**
Substituting a name makes the merge *harder* to see, not easier: `#` was
uninformative but visibly a fold, while `20260822` on a row that also holds
`20260821`'s run is specific, real and wrong, and `RUNS 2` then reads as two runs
of one workload rather than one run each of two. `label` now appends `+N` when the
fold erased the name **and** the group covers more than one raw `JobName`, with a
legend line shown only when such a row is on screen.

Narrow on purpose: an earlier round took `distinct_names` off the table as clutter
beside the name, and that judgement still holds for the ordinary row. This is not
the count returning -- it appears only where the substitution would otherwise imply
a singularity the row lacks.

The `--json` half of the reply needed nothing: that payload emits `g.name`, the raw
signature, not `g.label`, so machine consumers never saw the substituted name and
`distinct_names` has been beside it all along. Checked rather than assumed.

Two tests of this round's own had to change -- they asserted the bare `20260823`,
which is the behaviour being argued against -- and were updated deliberately, with
a new control that a single-name fold carries no marker.

### 4. Two sentences that disagreed on a sparse history

```
  baseline 0.0% over 2 placements; 2 nodes below threshold omitted
  No hangs recorded for #-# in this window, so there is nothing to attribute to a node.
```

The first says nodes were evaluated and withheld for want of samples; the second
says there was nothing to evaluate. Only the second can be right: with no events
recorded, the sample threshold is not what stands between the reader and a
verdict, so naming it points at a fix that would not produce one. The omission
count is now suppressed when `hits` is zero, and kept otherwise -- with events on
record those nodes *are* why the table is empty, and every other truncated view
here names its tail.

### 5. The released sdist carried a test suite that could not be collected

Not from the report. Found while verifying the four fixes above the way that
report's author verifies things -- their round 7 says so explicitly: *"I
re-verified both by downloading the released PyPI sdist, applying the patch,
installing into a clean venv, and re-running the original reproductions, because
the 'gates green' tables in the FIXES docs were measured in a working tree that no
longer exists."* That is the right instinct, and it is worth being able to serve.

Doing the same thing here:

```
$ pip download slurmpast==0.7.0 --no-deps --no-binary :all:
$ tar xzf slurmpast-0.7.0.tar.gz && cd slurmpast-0.7.0 && pytest -q
ERROR tests/test_extraction.py
ERROR tests/test_patterns.py
ERROR tests/test_portability.py
ERROR tests/test_sacct.py
ERROR tests/test_sizing.py
E   ModuleNotFoundError: No module named 'tests.conftest'
!!!!!!!! Interrupted: 5 errors during collection !!!!!!!!
```

There was no `MANIFEST.in`, so the sdist file list was setuptools' default, which
includes `tests/test*.py` -- a distutils legacy rule -- and nothing else under
that directory. `conftest.py` and `__init__.py` do not match `test*.py`. So the
sdist shipped 18 of the 20 files: every test module, and neither of the two that
make them importable.

Fixing only that exposed the same problem one level out, and this is the part
worth writing down: **this suite audits the repository, not just the package.**
Eight tests then failed on a correct build because what they audit had not shipped
either -- the README against the dependency pin in `.github/workflows/ci.yml`, the
prose in `docs/details.md` against the code it documents, the import declarations
in `tools/`, and every image `README.md` points at under `assets/`.

So the manifest grafts the whole source rather than the two missing files:
`tests`, `docs`, `tools`, `assets`, `.github`. The sdist goes from 369 KB to
1.4 MB, almost all of it `assets/demo.gif`, and in exchange the artefact PyPI
serves is one somebody can rebuild and re-verify. Measured from a freshly built
sdist, unpacked, `pytest -q` in a clean venv:

```
before   5 collection errors, suite does not run
after    1588 passed
```

**Why this belongs in a portability round rather than a packaging nit.** The only
way a claim like "works on any Slurm" gets checked is somebody on a cluster nobody
here has seen downloading the released artefact and running it there. A suite that
cannot be collected reads as a broken package, not a broken sdist, and the reader
has no way to tell those apart. It is the same failure as SP-1 in a different
register: confidently wrong output from a tool that is only wrong about itself.

`TestTheSdistShipsASuiteThatCanRun` pins the manifest against the whole of
`tests/`, so a helper added later is not silently left behind again; it fails with
`MANIFEST.in` removed. Its second test is the control on the *claim* rather than
the fix -- if `tests.conftest` ever stops being the importable path five modules
depend on, the reproduction above is describing something that can no longer
happen, and the class should be re-read rather than trusted.

#### The report found it independently, two days later, as SP-9

Filed with the same reproduction, the same root cause and the same fix, which is
the most useful confirmation this finding could get: it was the one item in the
round nobody had asked for, and an outside pass arriving at it separately settles
whether it was worth the detour.

Their version adds a number this write-up did not have — **nine of the eighteen
shipped modules import the missing file**, through two different spellings
(`from tests.conftest import …` and `from .conftest import …`), neither of which
can resolve without it. Checked against the fixed tarball, and the count matches
exactly:

```
conftest in tarball : 1          (was 0)
tests/__init__.py   : 1          (was 0)
modules importing it: 9
__pycache__ shipped : 0
```

They also offer a second option this round did not take: *"or mark the repo-audit
tests to skip when the repo scaffolding is absent"*. Grafting `docs`, `tools`,
`assets` and `.github` is the better half of that choice — those seven audits then
**pass** rather than skip, which is what makes `pytest` on an unpacked sdist a
gate rather than a gesture. Their own list of the seven is exactly the set that
grafting fixes, and a full run from the unpacked tarball is now `1642 passed`,
with nothing skipped.

Their `__pycache__` note was withdrawn in the same round and is correct to
withdraw: the tarball carries none, and a local `pytest` run is what created the
directory they saw.

### 6. A unit-less memory limit read as bytes, a million times too small

Not in `slurmpast.md`. It is in **`slurmwatch.md`**, under that package's SW-12,
because the author measured all three tools against the same inputs and tabulated
the divergence rather than splitting it across three files:

| input | slurmpast | slurmwatch | slurmate | Slurm's meaning |
|---|---|---|---|---|
| `4Gn`   | 4294967296 | 0 | 4096 MB | 4 GiB per node |
| `500Mc` | 524288000  | 0 | — | 500 MiB per CPU |
| `64GB`  | None   | 68719476736 | rejected | not valid Slurm syntax |
| `16`    | **16 (bytes)** | **16 (bytes)** | **16 MB** | **16 MiB** |
| `1.50T` | 1649267441664 | 1649267441664 | 1572864 MB | 1.5 TiB |

slurmate is the one that is right. `sbatch(1)` on `--mem=<size>[units]`: *"Default
units are megabytes."* Reading `16` as 16 bytes is wrong by 1,048,576x and silent,
and a memory ceiling a millionth of its true size makes every job on it look
catastrophically over limit.

Worth saying that this was only findable because the report cut across packages.
A per-tool pass would have shown `16 -> 16` with nothing to compare it against.

**The report's own fix is right in principle and wrong to apply as written.** It
says *"default a unit-less integer to MiB"*, which taken at face value means
changing the shared byte parser. `parse_bytes` also decodes `MaxPages` --
a *page count*, which this cluster emits bare --

```
$ sacct -u youzhi -S now-7days --format=MaxPages,MaxDiskRead,MaxRSS
0|0.00M|1924K
```

-- and `MaxDiskRead`/`MaxDiskWrite`, which are byte counters. The MiB rule there
would read a bare `312` as 312 MiB. So the convention now lives in a separate
`parse_mem_limit`, wired to the one field that is a limit (`ReqMem`), and
`parse_bytes` is untouched. `test_parse_bytes_still_reads_a_bare_counter_as_bytes`
is the control that stops the fix spreading.

**Latent on both clusters, and fixed anyway.** The report classes SW-12 latent
because Slurm 23.02 always writes an explicit unit. Midway3 was checked too, and
it agrees -- 20.11.8, and not one unit-less row in 30 days:

```
$ sacct -a -S now-30days -X --format=ReqMem | sort | uniq -c | sort -rn | head -4
 609511 4Gn
  44246 8Gn
  42875 12Gn
  24350 3810Mc
$ ... | grep -vE '^[0-9.]+[KMGT][nc]$'
0n
```

Widened to every distinct spelling on the cluster rather than the handful the
unit test names, because "no number moves" is the kind of claim that is easy to
assert and cheap to check:

```
rows (14 days, all users, -X):                1,168,741
distinct ReqMem spellings:                          471
spellings where the fix changes the answer:           0
```

Two clusters, two Slurm majors, 471 spellings, zero occurrences. It is fixed
regardless because
the thing that decides the spelling is a site's Slurm version and submit style,
which is the one axis this tool cannot see from here — and the failure mode is
silent, so nobody would report it as a bug either.

### 7. A requeued job's earlier incarnations were invisible

`sacct` reports only a job's *latest* incarnation unless `-D` is passed, and this
module contained no `-D`. Slurm requeues on `NODE_FAIL`, on preemption, and on
`scontrol requeue`, so a job can have run, died and gone back to the queue with
nothing here able to say so. Reproduced against Midway3's own accounting rather
than the reporter's:

```
$ sacct -D -j 53432121 -X -P -o JobID,State,Submit,Elapsed
53432121|NODE_FAIL|2026-08-17T10:08:59|00:27:49
53432121|COMPLETED|2026-08-17T10:48:35|03:41:52

$ slurmpast 53432121            (before)
job 53432121  COMPLETED
  ● TIME  ███████░░░░░  37.0%  · 03:41:52 of the 10:00:00 limit
```

Twenty-seven minutes and forty-nine seconds on a node that failed underneath it,
and not a word. For a tool whose one question is *what happened to my job*, the
requeue is frequently the whole answer -- "why is it still pending when I watched
it start" has no other cause.

Now:

```
  timing
    submitted   2026-08-17T10:48:35     started   2026-08-17T10:50:37
    ended       2026-08-17T14:32:29     queued for   1.0s
    requeued    1x · NODE_FAIL after 00:27:49
```

**One `Job` per id still comes out.** `-D` widens what is known; `_fold_incarnations`
keeps what is *counted* the same. The newest incarnation is the job and the ones
before it hang off it in `earlier`, so no rollup count, ranking, goodput figure or
post-mortem starts double-counting a job that ran once. That is deliberate: on
this cluster 773 rows in seven days are requeues out of 922,534, and a change that
moved every count for a 0.08% case would be a bad trade.

The row sits *above* the walltime line, because the walltime below it is this
incarnation's and a reader who has not been told the job ran before will take it
for the whole story.

**Ordering is by `Submit`, not `Start`.** Submit is the field Slurm advances on
requeue and the only one guaranteed present -- a requeued incarnation may never
have started, so `Start` is empty on either side of the comparison.

#### The near-miss, recorded because the controls are what caught it

The obvious way to key incarnations apart is `(JobID, Submit)`, which the report
suggests and which is right for *allocation* rows. Applying it to **step** rows as
well is wrong, and quietly so:

```
53432121        |2026-08-17T10:08:59|NODE_FAIL
53432121.batch  |2026-08-17T10:20:46|CANCELLED    <- the step's own start
53432121        |2026-08-17T10:48:35|COMPLETED
53432121.batch  |2026-08-17T10:50:37|COMPLETED|10822892K
```

A step's `Submit` is when the *step* began, not when the job was submitted. Keyed
that way, no step ever matches its allocation, every job in the tool loses its
step list, and the damage surfaces as `MEM  n/a` on a job whose memory was
recorded — an erasure that reads as missing data rather than as a bug. It was
caught by running the real job, and `test_the_steps_attach_to_the_incarnation_that_ran_them`
plus `test_an_ordinary_job_is_untouched` now fail against it. Both fail, which is
the point: it was never a requeue-only bug, it was every job.

Steps attach positionally instead — to the open allocation for that base id, which
is the order sacct emits them in — and a step arriving before its allocation still
goes to that id's first incarnation, as before.

#### The `--patterns` rule, now built

The round above recorded this as owed rather than skipped: the report asked for a
cross-run rule alongside the per-job row, and it was deferred because the
threshold needed data that did not exist until `-D` was being passed. It does now.

From Midway3's own seven days — 938,576 job ids, 680 requeued, across 12,130
workloads — **both** floors turn out to be necessary:

```
   100.0%    10 of 10       reference_#k_aldp_implicit_s
    83.3%     5 of 6        train_blending_model
    28.6%     6 of 21       _interactive
    12.2%   284 of 2332     Filtering
    12.0%    31 of 259      orca_spe
  ----------------------------------------------- the gap
     6.3%     7 of 111      qmmm_ro
     0.1%    99 of 159602   fy#_s#_#_e#.#
     0.0%     5 of 204607   aa#_s#_#.#m_#_e#.#
```

A count alone fires on that 159,602-run workload, where 99 requeues is background.
A rate alone fires on one job out of three. `REQUEUE_MIN = 3` with
`REQUEUE_FRACTION = 0.10` sits in the break between 12.0% and 6.3% and fires on
five workloads out of 12,130. Deliberately not `REPEAT_FAIL_FRACTION`'s 0.5: that
rule asks "does this workload mostly *fail*", which is the right question about a
failure and the wrong one about a requeue — 284 out of 2,332 is unmistakably a
node problem and nowhere near half.

**And the rule shipped wrong for an hour, which is the part worth recording.**
Run against the real cluster it said:

```
[WARN] This workload keeps being requeued
      284 of 1745 runs of Filtering in avieregg were requeued, 284 attempts in
      total; 284 were RUNNING. The abandoned attempts ran 4030-18:48:58 between them.
```

Four thousand days nobody spent, and `RUNNING` is not an outcome. Those 284 rows
are one array whose original incarnations were never closed:

```
53135721_304
    RUNNING  submit=2026-08-08T16:14:10  end=Unknown           elapsed=14-10:53:57
    CANCELLED submit=2026-08-13T11:28:19 end=2026-08-18T17:24  elapsed=5-05:14:41
```

`Elapsed` on an open record is measured to *now* — which is the same artefact the
`"N unterminated, excluded"` line exists to warn about, reproduced by a new rule
that forgot to apply the module's own standard. The rule now counts only earlier
attempts that **ended**, and that filter is what makes the finding mean anything:
of the 680 requeued ids, the 372 with a closed earlier row carry exactly the
states a requeue should have — `NODE_FAIL` 348, `REQUEUED` 27, nothing else —
while the open ones carry only the stale `RUNNING` they were left in.

After the filter, the same cluster reads:

```
[WARN] This workload keeps being requeued
      31 of 259 runs of orca_spe in lgagliardi-amd were requeued, 32 attempts in
      total; 32 were NODE_FAIL. The abandoned attempts ran 07:34:15 between them.
      → NODE_FAIL is the node, not the job. `slurmpast --nodes` attributes it ...
```

and `Filtering` is silent. The advice branches on the dominant state, because
`NODE_FAIL` points at `--nodes` and preemption points at QOS and checkpointing,
and telling either of those users the other's answer is worse than silence.


`Restarts` was not used: the report checked and it is not a valid sacct field on
23.02, and it is absent from 20.11.8 here too. The count comes from the rows.

### 8. Two sections asked for, one printed, nothing said

Every section branch in `cli.main` ended in `return 0`, so the first flag that
matched won and the rest evaporated -- rc=0, no message. Which one survived was
the order the branches happen to be written in, which nobody outside the file can
see. The report found four; the shape is general and the sweep here found more:

```
--overview --patterns  -> patterns only
--overview --nodes     -> nodes only
--patterns --nodes     -> nodes only        (not in the report)
--overview --sizing    -> sizing only       (not in the report)
--steps  (no job id)   -> ordinary overview, the flag a silent no-op
```

The report's framing is what makes this worth more than its severity suggests:
**both sibling packages reject this class of mistake loudly and name both flags**
-- `slurmwatch: ERROR: --once and --log are mutually exclusive`, `rapidu: error:
--sort density needs byte sizes and -c does not measure them`. A family of tools
that share a style should not disagree about whether a contradictory command line
is worth mentioning.

**Sections now compose, rather than being rejected.** The report offers both and
prefers this one, correctly: the default plain report already prints several
sections in sequence, so asking for two of them by name has an obvious meaning and
no reason to be an error. Order is fixed and independent of the branch order --
`overview, patterns, nodes, sizing`, the rollup first, then what recurs, then the
two screens that attribute it -- so `--nodes --patterns` and `--patterns --nodes`
produce the same bytes.

**`--json` refuses more than one.** It emits one document per section and there is
no defined way to concatenate two; picking a winner there is exactly the behaviour
being fixed, so the pair is named and refused with rc=2.

**`--steps` without a job id is refused**, rc=2, naming the flag and what to type
instead. `--help` already said "on a named job".

**Narrowed from the report: `--plain --json` is not a conflict.** It is listed as
"JSON emitted; `--plain` silently dropped", but `--plain` means *no dashboard* --
that is what its help says -- and `--json` satisfies that. Nothing is discarded.
Erroring would also break `slurmpast --json > file`, because the tty guard from
finding 2 sets `plain` itself on a redirect: the two flags are not merely
compatible, one of them is set *by* the other's normal use. Left alone, and said
here rather than quietly skipped.

#### The regression this nearly shipped, caught by an existing test

Making the sections compose meant deleting the `return 0` at the end of each
branch. That `return` was doing two jobs: it made the sections exclusive, and it
also terminated the branch's **`--json`** path. Removing it left `--overview
--json` printing its document and then falling through to print the per-job
payload after it.

Valid JSON followed by more valid JSON is not valid JSON, and nothing about the
output looks wrong -- eyeballing it shows a document. `json.loads` is what says
so, and seven existing tests in `test_cli.py` failed instantly with
`JSONDecodeError: Extra data: line 142 column 1`. `test_one_section_with_json_emits_exactly_one_document`
now pins it directly rather than as a side effect of tests about something else.

### 9. The one environment variable took anything, and misreported itself

`SLURMPAST_TIMEOUT` is this package's entire environment surface, and nothing in
this suite touched it. It accepted every input and quietly used the default:

```
SLURMPAST_TIMEOUT=garbage  -> rc=0, query runs normally
SLURMPAST_TIMEOUT=-5       -> rc=0, query runs normally
SLURMPAST_TIMEOUT=0        -> rc=0, query runs normally
```

`0` is the one that stings: a reader writes it meaning *no timeout* and gets 300
seconds, with nothing said in either direction. `garbage` was indistinguishable
from leaving the variable unset. Each is now refused by name, quoting the value
back, with the default named so the reader knows what unsetting gets them.

**A large value is honoured, not capped.** The report lists `999999` beside the
others, but nothing silently falls back there -- it is used. The variable exists
so a site whose accounting takes an hour can say so, and capping it would be the
same fault in the other direction. Said here because the row reads like a fourth
defect and is not one.

**Zero and negative are refused rather than read as "wait forever."** That is a
choice, and the reason is two findings up this same page: an unbounded wait is
what a redirect used to do before there was a tty guard, and a query with no
ceiling under cron is that failure again. Infinity is refused with them --
`float("1e999")` succeeds and `communicate(timeout=inf)` waits forever.

### 10. A sub-second budget printed as `0s`

`sacct.py` formatted the timeout with `%.0f`:

```
$ SLURMPAST_TIMEOUT=0.05 slurmpast -S now-2days --overview          # rc=2
slurmpast: sacct did not answer within 0s — the accounting database may be
unreachable. Narrow the window with -S, or raise SLURMPAST_TIMEOUT.
```

Which reads as *the tool used a zero timeout* -- its own defect -- rather than
*your 50 ms budget was too small*. The sentence then advises raising the variable,
which the reader cannot act on without seeing what it currently is. `%g`, as the
report suggests: `within 0.05s`, and a whole number still prints as `2s` rather
than `2.0s`.

The budget is also read once now and quoted from that, rather than called a second
time inside the failure branch -- the message should quote the budget actually
used, not re-derive it from an environment that may have moved.

#### One defect this fix introduced, found reviewing it rather than running it

Making `_timeout` raise turned a function that could not fail into one that can,
and it was still being read *after* the subprocess had been spawned:

```
_run:  Popen(...)          <- sacct starts
       budget = _timeout() <- raises on a bad SLURMPAST_TIMEOUT
```

Nothing reaps the child on that path -- the only cleanup in `_run` is the
`TimeoutExpired` branch, which a `SacctError` skips straight past -- so an invalid
variable left a real `sacct` running. It never showed up in output, in an exit
code, or in a test; a diff read is what found it. The read now happens before the
spawn, which is also simply correct: refusing a setting is no reason to have
started a query first.
`test_a_bad_value_is_refused_before_anything_is_spawned` pins the ordering by
counting `Popen` calls, and fails with the read moved back.

Both are pinned in `tests/test_portability.py`, the timeout message through the
real subprocess path with a command that genuinely outlasts its budget, because
the formatting lives in an `except` branch and a test that builds the string by
hand would pin the wrong thing.

**Also from that round, and checked rather than taken:** the four TUI bindings
(`n`, `s`, `w`, `p`) and hostile job-name rendering were reported working, with
one apparent double-count -- a workload reading `RUNS 1 / COMPLETED 1 / FLAGGED
1` -- dismissed in the report on the grounds that "flagged" means "has a finding"
and a run can complete and still be flagged. That reading is right, and it is what
`GroupStats.problems` computes; the columns were never a partition of each other.
Nothing to change.

### 11. A mis-matched log let the tool assert a cause it could disprove

The log-matching heuristic guesses when nothing records where output went, and
prints `matched by timing, not by name — verify before trusting it` when it does.
The hedge is real. What it does not do is stop the guess from producing a
confident wrong answer.

Reported from the second cluster: a job on a GPU-less partition failed with
`disk quota exceeded`, and a decoy file in the search directory -- unrelated name,
`touch -r`'d to the same mtime -- was matched. The report then read:

```
  log .../logs/some-other-run.err
      matched by timing, not by name — verify before trusting it

  findings
  [FAIL] GPU ran out of memory
        Device-side allocation failure in the log. This is NOT host memory —
        raising --mem changes nothing.
        → Lower batch size, enable gradient checkpointing, or shard the model.
```

For a job that allocated no GPU. One dim line of caveat against the highest
severity the tool emits, stated as fact and followed by four remediations; a
reader who trusts the loudest thing on the screen goes and shrinks a batch size
for a quota problem.

**`AllocTRES` already said so.** No `gres` entry means a device-side allocation
failure is not unlikely, it is impossible, and the GPU rules (`cuda-oom` and the
NCCL one beside it) are now gated on the job having held a GPU. This does not make
a mis-attached log right -- it is still the wrong file -- it stops the tool
asserting what its own record rules out. Only the GPU rules are gated: a traceback
or an import error in a mis-attached log is still a possible cause for any job.

### 12. With both streams present it read the empty one and called it silence

Same job, both real logs in the directory:

```
  log .../realname-A.out
  [WARN] Exited 3, but no log was found to explain it
        → Pass --log-dir, or set a predictable --error= path.
```

`realname-A.err`, holding `REAL CAUSE: disk quota exceeded on /scratch`, sat
beside it. The advice given was advice the user had already followed.

The cause is in the ranking. `time_candidates` ordered on `(trusted, |mtime −
End|)`, and Slurm touches an unused `--output` when the job exits -- so on a
failed job the 0-byte stdout is routinely *nearer* End than the stderr written
moments earlier, when the error actually happened. Two terms were added:

* **empty before distance.** A zero-byte file explains nothing whatever its
  mtime. This is what fixes the reported case.
* **suffix after distance.** `.err` before `.out`, tie-break only. Deliberately
  not above the mtime: timing is the signal this function exists for and the one
  measured to recover 135 of 148 runs on a real history, and letting the suffix
  outrank it would re-pick a different file for every job in a directory holding
  both streams. The report asked for `.err` to win *a tie*, which is exactly this.

### 13. And then a failed job read "nothing to flag"

Not reported -- exposed by fixing the two above, which is the reason to write it
down. With the real stderr routed in and no rule matching `disk quota exceeded`,
the screen showed the log path and `nothing to flag`. About a job that failed.

It had always been possible; the empty-`.out` bug was hiding it, because an empty
file took the "no log was found" branch, which at least said something. So the
fix for finding 12 turned a wrong statement into no statement.

A failed job with a log now ends with the log's last lines, at INFO and phrased as
an excerpt rather than a diagnosis:

```
  [INFO] End of the log, which names no cause this tool recognises
        REAL CAUSE: disk quota exceeded on /scratch
```

The tool cannot name a cause it has no rule for and should not invent one; it can
show the reader the file it found, which is what they would open next anyway.

### 14. The authoritative path, where the controller still has it

The report is right that the heuristic exists for a real reason -- on Slurm 23.02
`sacct -o StdErr` is refused outright, the fields having arrived in 24.05 -- and
right that `scontrol` knows anyway:

```
$ sacct -o StdErr        sacct: error: Invalid field requested: "StdErr"
$ scontrol show job N    StdErr=/scratch/.../realname-A.err
```

`controller_log_paths` asks it, and the answer feeds `recorded_patterns` as if
`sacct` had supplied it, so the certain name-matched tier resolves and the guess
is never reached. Verified against a job the controller still held:

```
scontrol show job 53404048  ->  ('/project/aaz/pg_task/backup.log',
                                 '/project/aaz/pg_task/backup.log')
```

**Only for ids the caller typed.** `--failed` and `--problem` can hold hundreds of
jobs, mostly old enough that the controller has forgotten them, and one subprocess
each to be told so is a cost with no return. The explicit-id branch is small and
is the case that is usually recent -- which is the whole window this works in:
past `MinJobAge` it returns nothing and the existing ladder takes over unchanged.
Never raises, on the pattern `site.read` already set for `scontrol show config`.

### 15. The collective fault had no device and no peer

`nccl` was a pure text match, like `cuda-oom` beside it, so the same mis-attached
log drew a second CRITICAL on a job whose entire allocation read
`billing=1,cpu=1,mem=200M,node=1`:

```
[FAIL] Collective communication fault
      NCCL markers in the log. A collective timeout is usually a symptom: one rank
      diverged, died, or is slow, and the others block on it.
```

No GPU for NCCL to be running on, and no peer to block on -- the finding's own
sentence describes a topology the job did not have.

The report's round 29 then audited all eight rule families to size the problem and
**narrowed** it: every metric-derived family already guards its preconditions
(`_parallel_rules` on `task_count <= 1`, `_gpu_rules` on `not job.gpu_count`,
`_io_rules` and `_cpu_rules` on their own floors). Only these two branches inside
`_exit_rules` can contradict the allocation. Two guards in one function, not a
systemic gap -- and that audit is why this is a small fix rather than a sweep.

**The `cuda-oom` guard was tightened to the identical test, not a similar one.**
It first shipped as `job.gpu_count or "gres" in (job.alloc_tres or "")`, which is
looser than the `if not job.gpu_count` that `_gpu_rules` uses. That difference is
the defect in miniature: on a job where the two disagreed, `cuda-oom` would fire
while the GPU-utilisation findings stayed silent, and the screen would hold two
findings disagreeing about whether the job had a GPU. `_io_explains_idle_cpu`
already sets that standard explicitly -- share the condition "rather than picking a
second threshold ... so the guard has to fire on the same jobs the other rule does,
not on a similar-looking set." Now it does.

#### Where the report's suggested test is wrong, and how that surfaced

Round 28 proposes "a `nodes > 1 or ntasks > 1` test to the collective rules". Taken
literally that is wrong, and the suite said so on the first run: eight existing
tests failed, five of them real NCCL fault shapes that must still be caught.

The reason is that **a rank is not a task**. This suite's own `healthy_job` is
`gres/gpu=3` on `node=1` with no `NTasks` recorded at all -- `task_count` is 0 --
and three GPUs on one node do collectives across each other. Tasks and nodes alone
do not count the ranks.

The guard is therefore a device *and* a peer, with GPUs counted among the peers:

| allocation | `cuda-oom` | `nccl` |
|---|---|---|
| `cpu=1,mem=200M,node=1` (the reported job) | no | no |
| `gres/gpu=1,node=1` | **yes** | no |
| `gres/gpu=3,node=1` | yes | **yes** |
| `gres/gpu=2,node=2` | yes | yes |

The middle row is the discriminating one: a single GPU is a device, so an OOM
stands; it is not a peer, so a collective does not.

### 16. SP-10's precondition, narrowed by the reporter and pinned here

Round 28 also narrowed its own round-27 finding: a decoy only wins when nothing
matches by *name*. Given a log named with `%j` in the job's WorkDir, that path is
found first and the decoy is never considered, so the exposure is "users with a
fixed log name" rather than everyone. Confirmed here:

```
chose: gpuless-48819454.err | inferred(guessed): False
```

`TestANameMatchBeatsATimingDecoy` pins it -- both that the named log wins and that
it is *not* flagged as inferred, since a name match is certain and must not carry
the timing hedge. Worth pinning for a second reason: the candidate ranking was
changed in the same round for finding 12, and an assertion that name beats timing
is what stops a later change quietly widening the blast radius again.

### 17. The CPU axis had no honesty rule, and a whole class of parallel job is invisible to it

`sizing.py`'s module docstring opens with "Four rules keep the advice honest", and
two of them are about a measurement that lies in a known direction: `Elapsed` on a
TIMEOUT bounds runtime from below, and `MaxRSS` under `jobacct_gather/linux` bounds
memory from above -- the second *worded from the cluster*, via
`site.maxrss_caveat()`. `TotalCPU` is the third such measurement and had no
equivalent, and it is the only one whose absence points at **shrinking** an
allocation that was in use.

`TotalCPU` is summed over the step's *process tree*. `parallelly::makeClusterPSOCK`,
which backs R's `plan(multisession)` and is that ecosystem's default
recommendation, reparents every worker to PID 1, so their CPU is charged to
nobody. Reported from a second cluster on a real job -- eight workers genuinely
running, 24 minutes of wall time against ~4 hours of serial work:

```
[WARN] Most allocated cores were idle
      Utilization 1.1% of 8 cores, i.e. about 0.1 cores of real work.
      → Try --cpus-per-task=1, unless those cores feed dataloader workers.
```

Taking that advice serialises the fan-out. The memory finding directly beneath it
was hedged; this one was not, from the same gather plugin.

**It is a cluster property, not a universal disclaimer.** Reparenting moves a
process in the tree but not out of its cgroup, so a `jobacct_gather/cgroup` site
counts those workers correctly and should be told so. `cpu_caveat()` branches the
same three ways `maxrss_caveat()` does, including the `None is not False` hedge
for an unknown site. `JobAcctGatherFrequency` is deliberately not read -- the
reporter's own three-arm control disproved it as the explanation, and encoding it
would put a wrong reason in the code.

Wired into both consumers. The `--sizing` line is the one that matters most,
because round 31 verified those `#SBATCH` directives get pasted into real scripts
verbatim and accepted by `sbatch` unmodified: an un-caveated undercount there is
*executed*, not merely read. Applied on the `lower` verdict only, since a `keep`
or `raise` is not endangered by a figure that is too low.

**A latent bug of the existing code surfaced while wiring it.** `cpu_advice`'s GPU
clause **assigned** `caution` rather than appending, so it dropped anything written
before it. Harmless while it was the first thing written; it would have swallowed
this caveat on every GPU workload. The three clauses are joined now.

**Caveated, not suppressed**, which the report argues for and is right about:
`_CPU_TIME_ALREADY_EXPLAINED` is for states where the number is garbage, and here
0.1 of 8 cores is real work really done -- just not all of it.

**Independently quantified, by a different tool on the same workload.** A later
round of the sibling package's report built both variants of this shape and summed
CPU per process over the job cgroup, which is the ground truth neither `sacct` nor
this tool can reach:

```
LONG    nprocs=16  own_cores=8.00  reaped_child_cores=0.00  total_cores=8.00
CHURN   nprocs=26  own_cores=0.09  reaped_child_cores=7.91  total_cores=8.00
```

Both genuinely at 8.00 of 8 allocated cores, against the `0.1 of 8` this tool
reports -- and `/usr/bin/time -v` on the identical R script puts `multisession` at
0.08 cores and `multicore` at 7.94, **103x apart** on the same work. That is the
size of the gap the caveat now names, measured rather than argued, and it settles
that the wording is not over-cautious.

It also confirms the direction is the only one available here: the same round found
that reading the job's cgroup *on the node* recovers the figure exactly at every
poll interval. That path is a live-monitoring capability this tool does not have
and should not grow -- a post-mortem runs after the processes are gone.

**The noop finding was left alone at first, and should not have been.** The report
separates two things this round had run together: the `looks_like_noop`
*threshold* needs a detector that cannot be built from `sacct`, but the *claim the
finding makes* does not. `"Nothing was computed."` is a statement about the job
read off a figure that only supports a statement about what was attributed -- at
CRITICAL, a severity above the WARNING already fixed. The sentence is now
conditional on the cluster, sharing `cpu_total_is_complete()` with the caveat
rather than re-deriving the branch: absolute where the cgroup makes it true,
`"No CPU time was attributed to it."` plus the caveat where it does not.

Three existing tests asserted the absolute wording, and *why* they did is the
point: `conftest` pins `jobacct_gather/linux` for the whole suite, so they were
asserting the over-claim under exactly the configuration where it is wrong. The
control for "a genuinely idle allocation keeps the original sentence" now pins a
cgroup cluster, which is where that sentence is earned, and a new test covers the
linux half.

**Still owed: the threshold.** `NOOP_CPU_SECONDS` is untouched. Moving it needs the
distinction between "idle" and "counted elsewhere" that `sacct` cannot supply --
the report's own argument against a detector -- and changing the floor without it
trades a wrong CRITICAL for a missed one.

The distinction worth keeping from this round is the report's: a **precondition**
guard asks whether a rule applies to a job; a **validity** guard asks whether the
number it reads is trustworthy on this cluster. Round twenty-nine sized the first
and found one gap. This is the first instance of the second.

`TestTheCpuFigureCarriesItsOwnLimits`.

### 18. A reported legend bug that was a measurement artefact, and a scale pass

A later round filed the `"#" stands for a name's digits` legend as printing when no
`#` row is shown, on the reasoning that it is appended "based on the data" while
only the top 25 of 560 workloads are displayed.

**Withdrawn: it already conditions on the rendered rows.** `render_overview`
computes `shown = groups[:limit]` and the legend tests `shown`, so a folded
workload below the cutoff cannot trigger it. The observation came from the
detection: `grep -cE '^\s+[0-9]+\s+#'` matches only a label that *begins* with
`#`, and a fold which keeps its letters does not.

```
labels        : ['fy#_s#_#_e#.#']
legend printed: True
starts with # : False   <- what the grep tested
contains #    : True
```

`fy#_s#_#_e#.#` is a workload from that cluster's own window, so a `#` was on
screen in exactly the shape the grep could not see.

The reporter's closing guess -- that finding 3's fix might retire the legend
entirely -- is right in one direction and wrong in the other. Substituting a real
name retires the *all-digit* fold, which is the only shape their grep matched;
a fold that kept letters still renders `#` and still needs the note. So the fix is
why the grep found nothing, and also why the legend is still needed.

Pinned either way, because nothing had asserted it:
`TestTheHashLegendFollowsWhatIsOnScreen` covers both halves, and the
below-the-cutoff half fails when the condition is widened to the full group set --
the defect exactly as filed.

**The same rounds ran both analytical engines at production scale for the first
time**, 24,570 job rows in ~25 s. Eight memory findings, and 70 nodes all reported
inconclusive with the multiple-comparisons argument stated in the output rather
than buried in a threshold. That matters because a rule that never fires and a rule
that fires wrongly are indistinguishable on a thin history, which is all either had
seen. It also confirms finding 4's scope from the opposite side: there `hits > 0`,
so "55 nodes below threshold omitted" is informative, which is why that clause is
suppressed only when nothing was recorded rather than removed. No further tests --
both surfaces are already covered, and adding more would repeat the mistake round
nine taught.

### 19. `--sizing` recommended a core count the partition cannot schedule

Found by running `--sizing` over a week of all-users data and checking whether the
48 emitted `#SBATCH` lines are schedulable. One was not: `twistedBD`, 401 runs, on
a partition whose nodes have 28 cores --

```
  --cpus-per-task   raise to 34   (from 28)
      the busiest run used 27.9 of 28 cores per task.
  #SBATCH --cpus-per-task=34
```

```
$ sbatch --test-only --partition=broadwl --cpus-per-task=34 …
allocation failure: Requested node configuration is not available
```

The reading was right -- the workload is saturated and would use more -- and the
value it advised raising *from* was already the ceiling. Nothing checked the
inference against the hardware.

`site.partition_ceiling()` reads `sinfo -h -p <part> -N -o "%c %m"`. Per **node**,
not per partition group: `sinfo -o "%c"` collapses a heterogeneous partition to one
row and marks it `32+`, where the number is the *minimum*, which is the opposite of
a ceiling. ~40 ms for a 605-node partition, cached, and it never raises -- no
`sinfo`, an unknown partition or unparseable output all give `(None, None)` and the
recommendation is untouched, because a wrong clamp suppresses advice a user needs.

Upward only. A downward recommendation was verified end to end on the second
cluster, and a ceiling cannot make a smaller request unschedulable.

**Clamping alone was the wrong fix, and the report's suggested wording is what
showed it.** Clamping 34 to 28 makes the verdict `keep`, which renders as
`already about right` -- a different wrong answer for a workload using 27.9 of 28
cores. There is no `--cpus-per-task` value that expresses "this needs a bigger
node", so saturation got its own verdict:

```
    --cpus-per-task   at this partition's ceiling
        the busiest run used 47.6 of 48 cores per task.
        ! Saturated at this partition's ceiling of 48 cores per node, so a larger request here
          cannot be scheduled — this workload needs a partition with more cores per node.
```

The measurement stays, because it is the evidence for moving partition. No
`#SBATCH` line is emitted and the dashboard filters on `actionable`, so nothing
unschedulable reaches either surface.

**Not done: naming a replacement partition.** The report notes several exist with
more cores. Choosing one needs account access, walltime limits and queue depth,
none of which `sinfo` answers -- and naming a partition the user cannot submit to
would repeat this defect one level up. The advice names the property to look for.

`TestAnUpwardAdviceCannotExceedTheNode`, including one test that fails against the
clamp-only version written first.

**The fix leaked into `--demo`, found by auditing it rather than by a test.**
Reading a partition's size means running `sinfo`, and `--demo` is meant to touch no
scheduler -- it already pins the synthetic `scontrol show config` because several
messages are worded from `JobAcctGatherType`. Instrumenting the subprocess layer
caught the new call going straight past that: `--demo --sizing` ran
`sinfo -h -p test` against the real cluster.

Invisible at the time, which is the reason to go looking rather than wait: every
CPU recommendation in the demo history is downward and the clamp only applies
upward, so the output was byte-identical either way. One upward recommendation in
the synthetic history and the demo would have begun differing by machine silently.
`demo.DEMO_PARTITIONS` pins the node sizes beside `DEMO_SITE` now, through a
`pin_partition_ceilings()` that mirrors the existing idiom.
`TestTheDemoAsksTheRealClusterNothing`, with the overview as the control that the
older pinning still holds.

### 1k. What the cross-package memory check settles, and the branch it cannot reach

A round of the sibling report compared all three tools on one job and used this
one as the reference:

```
slurmwatch (login node)  peak_bytes = 322,756,608  = 307.8 MiB
slurmpast  (post-mortem) 307.8 MiB of the 800.0 MiB limit
sacct      MaxRSS        315192K                   = 307.8 MiB
```

Exact agreement, which is worth having: it is the first independent confirmation
that this tool's memory reading is right rather than merely self-consistent. The
defect that round files (a 64% spread between vantages, from page cache the cgroup
counter includes and `MaxRSS` does not) is the sibling's, on its own on-node path.

**The part to record here is a limit of the testing, not a defect.** That cache
observation raises a fair question about `maxrss_caveat`'s cgroup arm, which tells
a reader the figure "is the step's real high-water mark rather than a sum over
processes" and says nothing about cache. Whether `sacct`'s `MaxRSS` under
`jobacct_gather/cgroup` is cache-inclusive is not answerable from the evidence
gathered: **both clusters in this exercise run `jobacct_gather/linux`**, so every
measurement so far exercises the other arm, and the sibling's 504 MiB came from
reading the cgroup directly rather than from `sacct`.

So the cgroup branch of that caveat -- and of `cpu_caveat` beside it -- is
reasoned, unit-tested, and has never been checked against a cluster configured
that way. Written down because "tested on a second cluster" is doing a lot of work
in this file, and this is a place where two clusters were not enough.

### 20. A clean pass that closed an earlier round's open question

A later round ran `--nodes --all-workloads` on the full cluster and filed no
defect. Two things it establishes are worth keeping.

**The `worse` verdict fires.** Round 34's controlled run returned 70 rows all
marked `inconclusive`, and its author could not tell from that whether the verdict
logic works or is unreachable. Uncontrolled, on 43,450 placements, `midway2-0651`
comes back **worse** at 57.1% against a 2.6% baseline. Reproduced here on the demo
history rather than accepted -- `midway3-0385` at 13/13 reads `worse`, and a
0/14 node reads `better` -- and it was already pinned, by
`test_worse_node_identified` plus four more sites exercising the same path. So no
test was added: the situation is round twelve's, not round nine's, and coverage was
checked before writing.

That question was worth closing regardless. A rule that never fires and a rule that
fires wrongly are indistinguishable from one sample, and only a second sample with
a different answer separates them.

**The `UNCONTROLLED` banner is a disclosure, and the control is what makes it one.**
`test_cli.py` asserts the line appears under `--all-workloads` and, immediately
after, that it is absent without the flag. Verified: one line uncontrolled, none
controlled.

The report's closing observation is the sharpest thing in it and is not something
the tool can say about itself: same cluster, same window, same metric yields "no
node is worse than the rest" when controlled for workload and one node at 57.1%
when not.

### 21. Three found in one pass: a locale that emits nothing, an environment with no identity, and a green all-clear meaning "no data"

**A non-UTF-8 locale produced zero bytes, not degraded output.** Four of five text
modes exited 1 with a `UnicodeEncodeError` and an empty stdout. `LC_ALL=C` is not
the case that bites -- PEP 538/540 coerce it -- but a *valid* 8-bit locale gets no
coercion, and `LANG=en_US` is ordinary in a site profile. Two layers: the
package's own glyphs, which `--ascii` could already switch if the reader knew to
ask, and **the data**, which it cannot touch. One job named `ファイル` in the
queried window took down every text mode for every user querying that window.

`sys.stdout.reconfigure(errors="backslashreplace")` at startup closes both;
`--ascii` is now selected from the encoding rather than requiring the flag.

*Proving which half does what took three attempts at the test, and the failures
are the interesting part.* The first version passed with the encode-safety
removed, because it ran `--demo` -- whose job names are all ASCII -- so only the
chrome layer was exercised: the tool's blind spot, reproduced in the test for it.
The second was a harness bug: `subprocess.run(text=True)` decodes the child's
latin-1 output as UTF-8 and raises, which looks exactly like a tool failure and
made auto-`--ascii` appear to break four modes when it breaks none. With both
fixed, the report's own claim stands -- the reconfigure alone closes every case --
so auto-`--ascii` is pinned for legibility (`##########` rather than
`\u2588\u2588\u2588...`) and not for survival.

**`sbatch --export=NONE` left no identity and three modes raised `OSError`** --
`--plain`, `--json`, `--overview`, the three a script uses, while the interactive
TUI printed one clean line. `getpass.getuser()` raises when the environment and
`pwd` both fail, which needs a cluster whose compute nodes carry no passwd entry:
invisible on the login node where the tool was written. `current_user()` now falls
back to `SLURM_JOB_USER` (which survives `--export=NONE`) and then the bare uid --
a real answer, not a placeholder: `sacct -u 940740146` returns that user's rows,
verified live. Raising `SacctError` at the end rather than broadening the `except`
was the report's call and the right one: the wider catch stops the traceback and
still leaves the tool unable to say whose history to read.

**`--sizing` reported "no data" in the same green all-clear as "correctly sized".**
On the reporting cluster 61 of 69 workloads were dropped, every one for lack of
runs and none for being correctly sized -- so the sentence offering both as
possibilities was 0% its first half. The filter now records why a workload left:
grey and counted for no data, green only for a genuine all-clear, and the dropped
workloads get their own tail line when others are shown. That second half was the
file's own standard, stated two lines below the filter that broke it.

`TestANonUtf8StdoutStillProducesOutput`, `TestTheUserIsResolvableWithoutAnEnvironment`,
`TestNoDataIsNotAnAllClear` -- including the test the report names by name.

### 22. Two cross-cutting checks that passed, and the one gap behind them

A round of environment checks across all four packages exercised two things about
this one and found no defect in either. Both were confirmed here rather than
accepted, and one turned up a hole in the tests rather than the code.

**An unwritable `XDG_CACHE_HOME` degrades silently** -- rc=0, full report.
Confirmed: `tui._clip_path()` is the only path in the package that writes state
anywhere, it already catches `OSError` and returns `""`, and the clipboard
fallback is not worth failing a report over.

The gap is that nothing asserted it. Three existing tests set `XDG_CACHE_HOME` and
all three point at a *writable* directory, so the failing side -- the side the
report exercised -- was never reached. That matters more than it sounds: "we never
write anything" and "we write and handle the failure" are indistinguishable from
outside, and only the second keeps working when the feature is actually used.
`test_an_unwritable_cache_home_costs_nothing` closes it, and fails with the
`except OSError` removed.

**The peak-memory figure agrees with the sibling tool on the same job**, from
independent sources -- theirs from the cgroup, this one from `sacct`'s `MaxRSS` --
1561.7 MiB against 1543.8 MiB on a job with 1.5 GiB touched. A disagreement there
would mean two tools in one suite giving contradictory sizing advice, so the
agreement is worth having on record. Nothing to change.

### 23. `-n` clipped the `--json` findings array invisibly, and `-n 0` was a usage error

Three parts, one of which departs from what the report asked for.

**The clip was undetectable.** `-n/--limit` bounds the `--json` `jobs` array, and
nothing in the payload said by how much: `summary.jobs` counts *every* job in the
window, so `len(jobs) < summary.jobs` is the normal state whether anything was
dropped or not. A monitoring consumer polling this would lose the oldest findings
silently as an account accumulates more than `-n` of them, with the JSON looking
exactly as complete as before. `summary` now carries `findings_jobs` and
`findings_jobs_shown`, so equality is the invariant a consumer checks.

The mirror image of finding 21 -- there the text view collapsed what the JSON
carried in full, here the JSON was the lossy one -- and the same cause: a
truncation decided at render time with no field recording that it happened.

**`-n 0` now means unlimited**, matching a sibling tool in the suite where it
already does. The previous rejection had a recorded reason -- it "renders a table
with a header, no rows, and a footer saying everything was omitted" -- which is
right about `[:0]` and says nothing about this meaning, since under it the table
renders everything. `-n -5` is still refused.

**Departed from the report on the third part.** It prefers exempting `--json` from
`-n` entirely, on the grounds that a machine payload has no rows. The limit is not
about rows: `targets = matches[:limit]` bounds the work that costs something *per
job*, resolving a log path and running the diagnosis, so lifting it makes an
unattended query over a wide window on a busy account arbitrarily expensive --
the invocation least likely to have anyone watching. With the count exposed and
`-n 0` available, a consumer can both see the clip and opt out of it; the help now
says what the flag actually does rather than being corrected to match it.

**Part two introduced a contradiction, caught by the test written for the recorded
objection.** `tail_summary` slices `groups[shown:]`, and `groups[None:]` is the
whole list -- so `-n 0` rendered every row and then announced that every row had
been hidden. One screen, two contradictory claims, which is precisely what that
line exists to prevent. Guarded at the source. Engaging with the old reason rather
than overriding it is what produced the test that found this.

`TestTheJsonSaysHowMuchItClipped` (including the test the report names),
`TestZeroMeansUnlimited`.

**Swept the rest for the same bug afterwards**, since one contradiction found by
accident is a reason to look for its siblings rather than to stop. Every view `-n`
governs was checked under `-n 0` for a claim that something is hidden:
`--overview`, `--plain`, `--sizing` and `--failed` are all clean, each having its
own tail line (`render_list`'s "… N more (raise --limit)", `render_sizing`'s
"below the N shown") that needed the same `None` guard.

`--nodes` does still print "N nodes below threshold omitted" under `-n 0`, and it
is right to: that is a *sample* threshold, not a row limit. Measured rather than
assumed -- the count is identical at `-n 0`, `-n 1` and `-n 25` -- and the test
that excludes `--nodes` from the sweep carries that measurement as its own control,
so the exclusion cannot quietly become an exemption.

### 24. The scan mode exited 0 while reporting critical findings, and the contract was unwritten

Deliberate, and the code said why: without job ids the cross-run patterns decide
the exit code, because a scan across a whole cluster would otherwise exit 1 almost
always and be useless as a signal. What made it a defect anyway is that the JSON
path computes the per-job verdict regardless -- the payload needs it -- and then
discards it, so `slurmpast --json || alert` is silent on precisely the mode anyone
would automate. Isolated with one OOM job: identical payload, `rc=0` scanning and
`rc=1` by job id.

`--help` now carries an `exit status:` section for 0/1/2, stating that `1` means
different things with and without job ids and that the reporting views always exit
0. `--strict` folds the per-job findings back in.

`--strict` reaches the text path too, and not merely for symmetry: the two branches
reach the same answer by different routes, the text one never running the per-job
loop, so there is no discarded value to reuse there and it diagnoses the jobs the
problem list just rendered.

**Two existing tests caught a mistake in the help text itself.** Writing `--` for
an em dash violates this repo's rule that the character be spelled so `--ascii` can
fold it, and the epilog's flag checker then read the bare `--` as a nonexistent
flag; listing the views inline tripped the same check on `--patterns,` with its
comma. Reworded rather than loosening a checker that is right to be strict -- the
alternative would have traded a documentation nit for a weaker guard on every
future example.

`TestTheExitCodeContractIsStatedAndOptional`, including both tests the report names.

### 25. Two production-scale confirmations, and one observation declined by its author

A round of the sibling report tested this package's array handling against other
users' real arrays -- the first time arrays larger than the reporter's own six-task
test were available -- and filed nothing. Both results are worth keeping.

**Arrays are exact at 500 tasks.** On `48810418`, 500 jobs and 500 completed, with
`core_hours_total = 41.09555555555557` against a hand-computed
`sum(Elapsed x AllocCPUS) = 41.095556`; on a 5-task array with one TIMEOUT,
19495.155555555557 against 19495.1556. 2.7 s for the 500-task payload. That run
also confirms naming job ids bypasses finding 22's `-n` clip, which is the
behaviour that fix deliberately kept.

**The SP-1 guard holds on a live throttled array.** `48781550` carries two finished
tasks plus the meta-record `48781550_[3-6]` for four queued ones. The loose JobID
guard -- chosen over the report's own anchored regex precisely because that spelling
deletes pending array ranges -- keeps the range id verbatim, excludes it from the
completion stats, and discloses it as `excluded_open_records: 1`. This is the first
time that decision has been exercised by another user's data rather than by the two
rows found in this cluster's history.

**One observation, declined by the reporter and not overridden here.** `_[3-6]`
stands for four tasks and is counted as one excluded record. Verified:

```
parsed ids    : ['48781550_1', '48781550_2', '48781550_[3-6]']
excluded_open : 1
```

Their reading is that "1 excluded record" is literally true, since sacct emits one
record and the four tasks do not exist separately yet, so they noted it rather than
filing it. That is right, and it is a close call worth writing down: the count feeds
the same `"N unterminated, excluded"` line that finding 1 was about, so under-stating
it by three is the same *shape* as that defect. What stops it being one is that the
missing three are not jobs the tool failed to show -- they are jobs the scheduler has
not created. Reopening it would need an argument that a reader expects task counts
rather than record counts there, and nobody has made one.

### 26. "Moved or deleted" about a file that is merely unreadable

`os.path.isfile` returns False for ENOENT and EACCES alike -- it swallows the
`OSError` -- so a log behind a mode-700 home was reported as moved or deleted. On a
shared cluster that is the normal case and not a corner: 104 of the 106 foreign
jobs naming a log path on the reporting cluster were unreadable rather than absent,
so the claim was wrong 98% of the time it appeared. It is also unreachable on a
single-user machine, which is where the sentence was written.

`logs.probe_path()` stats directly and branches on the errno -- `absent`,
`unreadable`, `unknown` -- and the renderer has three spellings where it had one.
The unreadable case names the owner, who is already on the record, so the reader is
told who to ask instead of being told something false about a file nobody could
see. `--json` gains `log_expected: {path, status}`, kept out of `log` itself
because that key is a path-or-null in every existing consumer.

**The fix broke a guard the report had just praised, and the output could not show
it.** `--no-logs` exists so the filesystem is not touched, and the text view
already withholds both spellings on that basis. Computing a status means stat-ing
the path, so the first version of the JSON half stat'd under `--no-logs` while
looking strictly more informative. Caught by counting `os.stat` calls, which is
also how the test asserts it -- reading the payload cannot distinguish a field that
was computed cheaply from one that cost a syscall.

That is the second time in three rounds that adding a field to `--json` quietly
reached into the filesystem or the scheduler (finding 18's `sinfo` in `--demo` was
the first). Both were found by instrumenting the call layer rather than by reading
the output, which now looks like the technique rather than the accident.

`TestAnUnreadableLogIsNotReportedAsDeleted`, including the test the report names
and a genuinely-absent control so the original wording survives where it is true.

**Its own third branch shipped untested**, found by auditing the fix rather than by
anything failing. `probe_path` was asserted for `absent`, `unreadable` and `found`;
the `unknown` arm -- the one that exists so a stat failing for any other reason is
reported rather than folded into a neighbour -- had no test, and its sentence had
none at all. An untested branch that only fires on an exotic errno is precisely the
kind that rots into whichever neighbour someone simplifies it into.

Closed with two real triggers rather than a patched `os.stat`, so the tests exercise
the errno handling and not a mock: a path component past `NAME_MAX` (ENAMETOOLONG)
and a symlink pointing at itself (ELOOP). Both fail if `unknown` is folded into
`absent`, and the sentence test also fails if it borrows either neighbour's claim --
which is the actual risk, since "moved or deleted" and "not readable by you" are
both wrong when the tool does not know which is true.

**And the key's shape was wrong, which the documented value count should have
caught and could not.** `log_expected` shipped conditionally -- absent when a log
was found or none was recorded. That is the right instinct for a *root* key, and is
why `dropped_rows` is still emitted only when non-zero: nothing documents a
root-key count, so a well-formed payload stays byte-identical. It is the wrong
instinct for a **per-job** key, because that count *is* documented -- "N values per
job" in the README and `docs/details.md` -- and a key that comes and goes made it 97
or 99 depending on the job.

The audit that pins that number passed throughout, because it counts one sample and
that sample has no recorded path. So the README was wrong for anyone whose job had
one, and the guard could not see it.

The key is now unconditional with both sub-keys, `null` where there is nothing to
say: one shape for a machine payload, and a count that is a property of the payload
rather than of the job. Documented figure updated 97 -> 99, and
`test_the_count_does_not_depend_on_which_job_it_is` measures four job shapes
against each other rather than one against a literal, so the next conditional
per-job key fails immediately instead of quietly making the prose wrong.

Auditing the rest of the per-job additions found nothing else: `timing.earlier`
from finding 12 is stable at any number of incarnations, because `leaves` counts a
list as one whatever it holds. Stable by construction rather than by care, so the
requeued shape is in that test too -- if the field is ever expanded from a list
into an object, the count moves and the guard says so.

### 27. Turning a technique that worked twice into a guard

Two rounds running, a new field reached outside the process from a path that
promises not to: `--sizing` running `sinfo` under `--demo`, and `--json` stat-ing a
recorded log path under `--no-logs`. Both were invisible in the output -- the
payload simply looked more informative -- and both were found only by counting the
calls. Two is enough to stop treating that as luck.

So the two isolation tests are now sweeps rather than single cases.
`TestTheDemoAsksTheRealClusterNothing` runs eleven invocations, every view flag and
their `--json` pairings and the single-job screen, and asserts zero subprocesses.
`TestNoLogsTouchesNoFilesystem` does the same for the filesystem, asserting no
recorded log path is stat'd under `--no-logs`.

Two things keep the sweeps from rotting, which matters more than the sweeps:

* **the mode list is checked against the parser.** A view added to the CLI and not
  to the list would be untested and *look* tested, which is exactly how both leaks
  got in. `test_the_list_of_modes_is_not_stale` asks `build_parser()` what it
  offers and fails if a view flag has no isolation case.
* **the `--no-logs` sweep has a positive control.** If nothing ever stat'd the
  recorded path, every assertion in it would pass vacuously, so one test asserts
  the probe *does* run without the flag.

Verified by re-breaking both original defects: the `--demo` one now fails
`--sizing --json` in the sweep, the `--no-logs` one fails `--json` and
`900002 --json`. Neither could be reintroduced silently now.

### 28. A 100% baseline blamed on sample size

At a 100% baseline no node can be worse than the baseline, so the node comparison
is unavailable for a reason no window can fix -- and the screen said *"No node
reached the 10 placements a comparison needs. A wider window is what fixes this."*
Following that costs a bigger query and returns the same non-answer. The useful
statement was already in the data: the workload completed on none of the 44 nodes
it touched, so no node is the problem.

`nodes_empty_reason` now checks the baseline first and says that instead.

**The gate the report's sketch lacks.** Applying the check unconditionally broke
seven existing tests, and reading them is what showed the sketch was incomplete
rather than the tests being in the way: their fixtures are thin *and* degenerate --
four all-hung runs are also a 100% baseline -- and concluding "this is a workload
failure" from four placements is the same over-reading in the other direction. So
the branch is gated on `trials >= MIN_SAMPLES`; below it the sample size really is
an obstacle too and the original sentence stays.

**The 0% mirror needs no branch**, checked rather than skipped: `baseline` is
`hits/trials`, so `hits > 0` implies `baseline > 0`, and `hits == 0` is caught one
branch earlier by a sentence that is already the right answer. A test records that
so it reads as considered rather than missed.

Scoped to the no-table case on purpose -- `render_nodes` returns early on any
non-empty reason, so firing it where rows exist would replace a real table with a
sentence.

**Left undone: falling back to another workload.** The report raises it and answers
it: the workload control is why this screen is trustworthy, and quietly analysing a
workload the reader did not ask about trades a non-answer for an answer to a
different question.

`TestADegenerateBaselineIsNamedRatherThanBlamedOnSampleSize`, including the test the
report names.

### 29. `--json` never said the data was synthetic, found by checking a compliment

The cross-package review named this package's `--demo` marking the pattern the
other tools should copy: *"the marker sits in a field the output always renders, so
it cannot scroll away or be dropped by a consumer."* Verifying that rather than
accepting it found it was not true of the machine path.

```
  --demo --json:  summary has no window; "synthetic" appears nowhere in the payload
```

So a consumer of `--demo --json` could not distinguish simulated data from real --
which is the same defect that review files against the sibling tool three rows
above, in the same table (*"no in `--once --json`, 3438 bytes of telemetry, zero
markers"*). Only the overview had been looked at here, and only the overview and
`--plain` render the window line at all.

Fixed by carrying `history.window` into every payload root, which is worth having
on its own account: nothing in the payload previously told a consumer what period
the numbers covered, synthetic or not. A real window now reads `"last 2 days"`.

The `--demo` risk here is milder than the sibling's -- a flag the user typed, not
an environment variable that can arrive from a CI wrapper or a stale `export` --
but the payload gap was identical, and being cited as the model is a reason to
check rather than a reason to relax.

**A test-harness trap worth recording**, since it cost two attempts: `Sacct().fields`
negotiates against whatever `sacct` is on the runner's PATH, so on a real cluster
the probe answers 80 fields while `conftest.row()` builds 85 -- every row is then
dropped as shifted and the fixture silently yields no jobs. Fixtures must pin
`_FIELDS` for both halves, which the older tests do.

`TestTheSyntheticMarkerReachesEverySurface`, six surfaces plus a real-window
control, all seven failing without the fix.

### 1c. SP-1 is worse than its own report first said, and the escalation is right

A fourth round of the midway2 pass built three jobs with genuine failure modes on
that cluster and asked the tool why they died. It then retracted round 1's own
conclusion, which had been:

> "Not corrupted: the 11 real job records survive … This is a count/garbage bug,
> **not a data-loss bug**."

That held only for the aggregate views, which filter phantoms through `usable()`.
`cli.main` sets `matches = jobs` on the explicit-id branch and filters nothing, so
the headline command rendered a *phantom* instead of the job asked for:

```
$ slurmpast 48819165 --plain
  [INFO] Accounting record is not closed
        State=? with End=Unknown. Elapsed (n/a) is measured from start to *now* …
        → squeue has never heard of it, so the job is long gone and the record
          was never closed.

job "  ?
  ● TIME   ░░░░░░░░░░░░░░░░░░          n/a   · n/a of the n/a limit
  job
    name             n/a
```

named `"` for a quote character out of the wrap script, every field `n/a`, and the
whole post-mortem printed twice. The truth was `OUT_OF_MEMORY` four minutes
earlier, with `slurmstepd: Detected 1 oom_kill event` sitting in the log. The
report's contrast isolates the trigger exactly: of its three jobs, the only one
that misdiagnosed was the only one whose `SubmitLine` spanned more than one line.

So this was never a reporting nit. A user asking the one question the tool exists
to answer got a confident wrong answer, not a degraded one.

**No further code change.** The fix above already covers it -- phantoms cannot be
produced, so the id branch has only the real record to render. Verified through
the real runner rather than by handing `parse` some text, because the damage lived
between the parser and the id branch:

```
job 48819165  OUT_OF_MEMORY
  ● TIME   █░░░░░░░░░░░░░░░░░         6.0%   · 36.0s of the 00:10:00 limit
  ● MEM    ██████████████████       100.0%   · 100.0 MiB of the 100.0 MiB limit
  job
    name             oomjob                          partition        build
    submitted as     python - <<'PY'
                     buf = 'x' * (600 << 20)
                     …
  [FAIL] Host memory exhausted
```

One block, the real name, the real state, the real cause, and the wrap script
rendered whole. `TestTheSingleJobPostMortemOnAMultiLineWrap` pins all four; three
of its four fail against the reverted tree with precisely the output above, and
the fourth is marked in its own docstring as supporting rather than
discriminating, because the phantoms it would otherwise catch print those same
lines by being them.

Recorded because the *severity* changed and nothing else did: had the report
stopped at round 1, this fix would have looked optional.

### 1d. The report bounded SP-1's reach itself, and the bound holds

Round 1 named `index.py`'s search as somewhere the phantoms might also have got
to -- "anything iterating raw `jobs` is not [safe]: check `index.py`'s search
index". A fifth round tested it, on a one-day history where the garbage
outnumbered the real records 3:1, and found nothing: searching the TUI for a
string that existed *only* inside a phantom matched no workload.

Confirmed here by reading the path rather than taking the result. Every consumer
of the model in `index.py` goes through `usable()` -- `group_jobs` at
`index.py:189`, `History.usable_jobs` at `453`, the `--failed`/`--problem` list
at `cli.py:846`, and the TUI's job list at `tui.py:1098` -- and `usable` drops an
open-ended record, which every phantom was.

So SP-1's confirmed reach was exactly the two surfaces fixed above: the
`"N unterminated, excluded"` count, and the single-job post-mortem. Not the
workload rollup, the TUI job list, the search index, `--nodes`, `--patterns` or
`--sizing`.

**No code change, and the scope was deliberately not widened to match the
worry.** Recorded because an unwritten negative result gets re-investigated -- and
because the two surfaces that *were* affected were both reached by a path that
does not call `usable()`, which is the property to check if a third one is ever
added.

### 1e. Round 9 found nothing, and that is what needed pinning

A ninth round tested the log reader the way it actually gets tested on a cluster:
a `.err` that is invalid UTF-8 -- what MPI, CUDA and Fortran tooling emit -- and
40 MB on a single line, with the real error buried after the noise. It reported a
clean pass: no crash, 17 MB peak RSS against the 40 MB file, a 1,572-byte report,
and `CUDA error: out of memory` correctly found past the padding, with the
GPU-versus-host-memory distinction in the advice. Its own words: *"Nothing to fix
here."*

Correct on all counts, and reproduced here rather than accepted. Same file shape
built locally:

```
bytes: 39,999,670
Path.read_text() -> UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 30
read_tail()      -> 262,144 chars, 0.00s, and the real error is in it
```

`logs.MAX_TAIL_BYTES` is 256 KiB and `read_tail` seeks to `size - max_bytes`, so
the file is never slurped; `raw.decode("utf-8", "replace")` is why the bad bytes
do not raise. Both were already right.

**What was wrong is that nothing in this suite said so.** `read_tail` appeared in
these tests exactly three times and was monkeypatched on all three
(`test_tui.py:773,833,849`), so the function itself had no coverage at all: not
the decode, not the cap, not the seek. A negative result nobody pinned is one
line of refactoring away from stopping being true, and this is the suite's
recorded failure mode -- tests that assert less than they appear to.

`TestAHostileLogDoesNotTakeTheReaderDown` pins six properties, and the three that
matter were each checked against a deliberately broken reader:

| regression introduced | what fails |
|---|---|
| `decode("utf-8")` without `"replace"` | the invalid-UTF-8 test, and both that read the file |
| `seek(0)` instead of `seek(size - max_bytes)` | the bounded-read test |
| `read(max_bytes)` from the head | the error-after-the-noise test |

The controls are a small clean log returned whole -- bounding must not start
truncating ordinary logs -- and the `\r` normalisation the function documents as
its reason for existing, which a fix aimed at hostile bytes must not cost.

Fixtures use four times the cap rather than the reported forty megabytes, so the
suite stays fast; the property is "bounded by `max_bytes` whatever the size", and
four times tests it as well as a hundred and sixty does. No source changed.

### 1f. SP-1's real trigger is wider than `--wrap`, and the fix already covered it

A tenth round widened the newline bug again. Round 4 had pinned it to a multi-line
`sbatch --wrap`; it reaches **any** multi-line field in **any** row, including
step rows. Job 48819348 was submitted the tidy way, from a script file, so its own
`SubmitLine` is the single line `sbatch steps.sh` — and asking for that one job id
still printed four post-mortems, three of them lines out of a heredoc belonging to
step `.1`, an ordinary `srun ... bash -c`.

That is a bigger deal than the `--wrap` case, and the report says so correctly:
the user did nothing unusual, and round 4's implicit advice — avoid multi-line
`--wrap` — would not have helped. The two shapes also fail differently: a
multi-line **job** row *replaces* the real record with a phantom, while a
multi-line **step** row leaves the record correct and appends fabricated
post-mortems under it.

**No code change.** The boundary rule asks whether a physical line's first field
looks like a JobID, and `48819348.1` does while `from slurmwatch import slurm`
does not, so step rows were never a separate case for it. Verified rather than
assumed — the fixture is the reported job, and it yields one record with the step
attached and no phantom:

```
records parsed : 1
job ids        : ['48819348']
steps          : ['48819348.1']
```

`TestAStepRowsMultiLineFieldMakesNoPhantoms` pins it, with the control that
rejecting the heredoc fragments must not also cost the step itself. Worth pinning
even though nothing changed: the report named this a distinct trigger, and a rule
that happens to cover a case should be shown to cover it.

Also in that round, and worth carrying over: **`--steps` is not broken.** The
report began writing it up as "drops every srun step — shows 2 of 6" and then
retracted it as its own `head -22` truncation. Checked here anyway, because a
retracted finding is still a place to look: `report.py:352` iterates `job.steps`,
and `Job.steps` and `work_steps` are both right. No finding.

### 1g. Round 12: the pattern engine fires, and this one was already pinned

Rounds 1, 4 and 10 all reported "no cross-run pattern met its evidence threshold",
which was true on thin data and left the feature unexercised. A twelfth round
built the data: three identical runs of a job asking `--mem=120M` and needing
~900 MB, all `OUT_OF_MEMORY`. It fired correctly, and the report singled out the
discriminating clause — *"the request has not moved"* — as the part that makes it
useful, because a user iterating on a memory request and a user resubmitting the
same failing one want opposite advice.

Reproduced here through the rule itself:

```
code='memory-unchanged'
title='The same memory request keeps being OOM-killed'
evidence='3 OOM kills for oomloop, every one of them at --mem 40.0 GiB: the request has not moved.'
action='Nothing has been tried yet: ... Measure the working set once ...'
```

**Nothing to fix, and — unlike round 9 — nothing to pin either.** The branch has
its own code (`memory-unchanged`, not `memory-search`) and four tests already
covering it: that it is named as what it is, that it is *not* told to stop
stepping, that a real search keeps the other wording, and that the two shapes keep
two codes so `--json` can tell them apart (`test_patterns.py:633-661`).

Recorded because the round-9 lesson pointed the other way and it would have been
easy to add a second set of assertions for a branch already covered. Coverage was
checked before writing, not after.

### 1h. Round 13: a mixed-outcome array, and a premise worth correcting

A 4-task array with two tasks OOM-killed and two completed rolls up correctly --
one workload, four runs, `completed 2 / flagged 2` -- and the round filed no
finding. Reproduced here and confirmed:

```
name='mixedarr' total=4 completed=2 failed=2 problems=2
headline: 2 of 4 jobs failed
```

**Pinned, because nothing covered it.** The rollup's own tests build separate
submissions; no test anywhere folded the *tasks* of one array into a workload and
checked the split. An array whose tasks disagree is the ordinary shape of a
parameter sweep, and it is exactly where a rollup that keyed on the array id
rather than the task, or took the first task's state for the group, would be wrong
with nothing failing. `TestAMixedOutcomeArrayAggregates`, with an all-completed
array as the control so a 2/2 split has to come from the tasks and not from the
shape.

**The threshold observation rests on a premise that is already false.** The round
noticed that two OOM tasks inside one array did not trip the memory rule while
three separate submissions did, and wondered whether the rule should *"ever count
array siblings"*. It already does. The grouping key is `(folded name, partition,
kind, user)`, which every task of an array shares, so siblings have always been
evidence:

```
2 OOM array siblings -> no finding
3 OOM array siblings -> ['memory-unchanged']
4 OOM array siblings -> ['memory-unchanged']
```

Two is quiet because the bar is three, not because they are siblings.

**Left at three, deliberately.** The suggestion behind the observation is a good
one -- two *simultaneous* identical tasks dying at the same request is arguably
stronger evidence than three sequential ones, because the user had no chance to
react between them. It is also not a defect, the report did not file it as one,
and acting on it means a second and lower threshold justified by an intuition
nobody has data for. `BISECTION_MIN_OOM` is one number that currently means one
thing.

`TestArraySiblingsAlreadyCountAsEvidence` pins both halves, and the pair is what
makes the claim legible: exempting arrays from the rule fails the three-sibling
test while the two-sibling test keeps passing, which is how a reader can tell the
silence at two is the threshold and not the shape.

### 1i. A test that asserted less than it appeared to, found auditing my own

With the report quiet, the round's own diff got the review. The source half turned
up the spawn-ordering defect recorded under finding 9; the test half turned up
one of the thing this suite is on record as being bad at.

Every new class had been checked against a deliberately broken version of what it
guards -- except three, which had been reasoned about instead. Two survived the
check. The third did not:

```python
def test_the_job_row_is_the_one_rendered(self):
    """The reported symptom was three extra post-mortems below the real one."""
    out, _verdict = report.render_job(self._jobs()[0], ...)
    assert out.count("● TIME") == 1
```

It passes against the broken parser. Handing `render_job` a single `Job` gets a
single block back whatever the parser did -- the extra post-mortems the docstring
names appear on the `cli.main` branch where `matches = jobs` decides *how many*
jobs there are, which this never reached. The assertion was true, the docstring
was true, and together they claimed to test something neither touched.

Driven through `cli.main` now, and the mutation that used to fail one test in the
class fails two.

The two that held up, for the record: the mixed-outcome array class fails when a
group takes its first task's outcome for the whole array, and the requeue class's
open-record control fails when the closed-attempt filter is dropped. Each of the
three was checked by breaking the code, not by reading the test.

### 1j. The report's thesis, tested against this round's own tests

Round 20 ran each released sdist's suite on the second cluster and drew a
conclusion about all four packages rather than filing a defect:

> slurmwatch passes 837/837 on the cluster where this directory documents fifteen
> portability defects … every finding here lives at a boundary the tests mock.
> … a green suite is evidence about the code's internal consistency, not about
> its portability. The two tests that *did* break are the ones that touched the
> real environment or the real artifact.

That is right, and it is worth checking against this round's own additions rather
than nodding at. Most of them do mock the boundary -- fixture text through
`parse`, a fake `_run`, `cli.main` under `--demo`. Three do not, and they are the
three that matter: the hostile-log class writes a real 1 MB file and reads it, the
timeout class spawns a real process that genuinely outlasts its budget, and the
sdist class inspects the packaged artifact.

**Except the last one did not, and finding that out is the whole value of taking
the point seriously.** It read `MANIFEST.in` and reasoned about what a build
*would* contain, with a docstring defending the choice on the grounds that a build
needs `build` installed. Both halves were wrong: `build>=1.0` is in this project's
own `[dev]` extra and CI installs it, and a manifest is a description of an
artifact, not the artifact.

Rewriting it to build a real sdist was not enough either. Built in place, it
passed with `MANIFEST.in` **deleted outright** -- setuptools reuses
`src/slurmpast.egg-info/SOURCES.txt` when it is there, and a developer tree always
has one, so the test was still reading a cached description one layer further
down. It now copies the tree without the egg-info and builds from that. Three
mutations, three distinct failures:

| mutation | what fails |
|---|---|
| `MANIFEST.in` deleted | all three tests |
| `graft tests` → `include tests/conftest.py` | the tests-coverage test |
| `graft assets` dropped | the repo-audits test |

The general lesson is the report's and it is not new to this file, but the
specific one is: a test named after an artifact will happily read something that
merely describes it, and twice in a row here it did.

#### And the sacct boundary now has a differential test, where there is a Slurm

The other half of the same point. `test_agrees_with_the_local_scheduler` has long
checked the nodelist expander against `scontrol show hostnames` and skipped where
there is no scheduler; nothing did the equivalent for the field negotiation, which
is the boundary SP-1 came through and the first thing to break on an unfamiliar
release. Every other test of the parser hands it a fixture, and a fixture cannot
know that `SubmitLine` does not exist before 21.08 or that `Reserved` became
`Planned` in 23.02.

`TestTheFieldProbeAgreesWithTheLocalSacct` asks the local scheduler instead: that
every negotiated field appears in its `--helpformat`, that the assembled query is
accepted rather than answered with `Invalid field requested`, and that the
delimiter negotiation settled on one of its two branches. It skips without a
Slurm, and skips rather than fails where one is present but its accounting cannot
answer -- an unreachable database on a login node is the environment's state, not
this package's defect.

It runs in 0.8s here and catches the failure it exists for: with the probe forced
to fail, so the full wish list is used, all three fail on this cluster's Slurm
**20.11.8** because the list then contains `SubmitLine`. That is precisely the
shape of bug this suite could not previously see.

### Consequence for the numbers

* **`slurmpast <jobid>` stops answering with a different job.** Any job submitted
  with a multi-line `sbatch --wrap` was rendered as a phantom -- unknown state,
  every gauge `n/a`, an "Accounting record is not closed" finding -- and now
  renders itself. This is the largest user-visible change in the round, and the
  exit code moves with it: the OOM above exited 0 as an unreadable record and
  exits 1 as a diagnosed failure.
* **The parser fix moves a count that was wrong, and no measurement.** Any history
  containing a multi-line `sbatch --wrap` loses its phantom records, so
  `excluded_open_records` -- the `"N unterminated, excluded"` line, and the same
  figure in `--json` -- falls to the true number. On the reported history that is
  47 → 2. Real job records were never corrupted: the 11 real rows parsed correctly
  before and after, so no rate, ranking or hour total moves. Anything iterating
  raw `jobs` rather than `usable()` sees 45 fewer objects.
* **`SubmitLine` now arrives whole** where it holds a newline, so the job screen
  shows the script rather than its first line.
* **A redirect changes output completely, from ANSI to the plain report**, and
  from hanging to exiting. Any script that was piping slurmpast and timing out
  now gets text and an exit code. Nothing changes in a terminal.
* **Two labels change on screen and one in `--json`:** a workload whose folded
  name kept no letter is now shown by a real job name, in the overview table, on
  `--nodes`, and in `--nodes --json`'s `workload` field. A consumer matching the
  literal `#` or `#-#` sees a name instead; one matching a name still does.
* `--nodes` drops the omission clause on a window with no recorded events.
* **Neither GPU finding appears for a job that held no GPU, and the collective
  one also needs a peer** -- one GPU on one node can still be reported as OOM but
  no longer as a collective fault. **A GPU finding no longer appears for a job that held no GPU**, and a failed job
  with an unreadable-to-the-rules log gains an INFO excerpt where it previously
  said nothing. On the explicit-id path a job the controller still remembers now
  resolves its log by name rather than by mtime, so some post-mortems attach a
  different -- correct -- file than before.
* **`SLURMPAST_TIMEOUT` now refuses what it used to ignore.** Anything that is not
  a positive finite number exits 2 where it previously ran with the 300s default.
  A script exporting a junk value was getting the default and now gets an error --
  which is the point, but it is a behaviour change rather than only a new message.
* **A workload requeued 3+ times and in 10% of its runs gains a `--patterns`
  finding.** New output where there was none; on this cluster it fires on 5
  workloads in 12,130 over a week, so most histories will never see it.
* **Two section flags now print two sections.** Anyone who was passing a pair and
  reading the one that came out gets more output than before, in a fixed order.
  Two combinations become errors where they were silently accepted: `--json` with
  more than one section, and `--steps` with no job id -- both rc=2, both naming
  what to do instead. A single section, with or without `--json`, is byte-identical.
* **A requeued job gains a `requeued Nx` timing row and a `timing.earlier` array
  in `--json`**, and `--json` goes from 96 values per job to 97. No count, rate or
  ranking moves: `-D` widens the query, and the incarnations fold back to one Job
  before anything counts them. On a cluster where nothing was ever requeued, no
  output changes at all.
* **A unit-less `ReqMem` now reads as MiB, so `mem_limit_bytes` moves by
  1,048,576x where it occurs at all** -- and with it the MEM gauge, the
  over/under-request findings and `--sizing`'s memory advice for those jobs. No
  row on either cluster checked has that spelling, so no number here moves; on a
  site that does have it, every memory figure for those jobs was wrong before and
  is right now. `parse_bytes` is unchanged, so no byte *counter* moves anywhere.
* **The sdist grows from 369 KB to 1.4 MB** and the suite inside it runs. Nothing
  in the installed package changes -- the wheel is unaffected, and `graft` only
  adds files to the source archive -- so this is a cost paid by whoever downloads
  the sdist and a capability gained by whoever wants to verify it.

### What was verified and not changed

* Everything the report lists under "Works correctly (do not fix these)" was left
  alone: field probing against `--helpformat`, the `SLURM_TIME_FORMAT` guard, the
  locale neutrality, the `-S '-7days'` rewrite, the nonexistent-user error, the
  `--all-users` scaling, and the exclusion of still-running array tasks.
* The report's own two retractions were not re-litigated.
* **One factual claim in the report is wrong, and this cluster is the proof.** It
  says "Slurm has recorded `SubmitLine` since 20.11, so this is live on any
  reasonably current site." Midway3 runs **20.11.8** and rejects the field
  outright:

  ```
  $ sacct --version
  slurm 20.11.8
  $ sacct -j 53488568 --parsable2 --format=JobID,SubmitLine
  sacct: error: Invalid field requested: "SubmitLine"
  ```

  21.08 is the release that added it, which is what `_records`' docstring already
  says. Nothing follows for the fix -- the field probe drops `SubmitLine` on 20.11
  exactly as it should, which is *why* Midway3 could never have surfaced this bug
  -- but the report's inference that the trigger is live everywhere current is
  wider than the evidence. On a 20.11 site it is unreachable through `SubmitLine`,
  and reachable only through `Comment`, `AdminComment` or `WorkDir`.
* 1560 tests before, **1753 after** -- 193 new, one per fix and its control. Each
  new test was run against the reverted tree, or against a deliberately broken
  version of what it guards where there was no bug to revert: 48 fail there and 34
  pass, and the 34 are the controls plus one supporting assertion that says so in
  its docstring.
  The last of them, `test_a_pending_array_range_is_not_mistaken_for_a_continuation`,
  is a control on the *fix* rather than the bug: it fails against the stricter
  JobID guard the report asked for, which is the only way a reader can tell that
  narrowing was a decision and not an omission.
* `ruff`, `ruff format`, `mypy` and `pytest` all clean.

## Round thirty-two — nothing found, and what was looked at

No code changed this round. The value of the round is the list below, so a later
one does not spend itself re-checking the same ground.

### The one thing that was wrong: a test of mine, not the code

Rounds twenty-two to thirty-two were never pushed, so none of them had reached
CI's matrix. The first push failed the **Oldest supported Textual** job:

```
FAILED test_the_job_list_adds_each_row_once  - AssertionError: 800 add_row calls for 400 rows
FAILED test_the_overview_adds_each_row_once  - AssertionError: 16 add_row calls for 8 rows
```

Round twenty-three's guard was written against the locally installed Textual
8.2.8 and its tests asserted `add_row == row_count`: exactly one build per screen.
Tracing on 0.86 -- rather than guessing, which round twenty-three's own docstring
records getting wrong twice -- showed the guard is fine and fires correctly:

```
  0 OverviewScreen rows=8 guard_fired=False layout=(('#',4),('JOB NAME',25),...,('CPU / GPU-HOURS',17))
  1 OverviewScreen rows=8 guard_fired=True  layout=(same)
  2 OverviewScreen rows=8 guard_fired=False layout=(('#',4),('JOB NAME',22),...,('COMPLETED',9),...)
  3 OverviewScreen rows=8 guard_fired=True  layout=(same)
```

Textual 0.86 lays the screen out at one size and then at its real one, so there
are two *genuinely different* layouts -- the second gains a `COMPLETED` column --
and the guard suppressed the duplicate within each pair, which is precisely what
it promises: "whether the table already holds exactly this layout and these rows".
It never promised one build per screen. That is a coincidence of newer Textual,
where a screen pushed onto a laid-out app already has its size.

So the test asserted more than the code claims, and the two tests now check the
contract instead: no `(layout, rows)` signature is ever built twice, and the
`add_row` count is one build per *distinct* layout. Both pass on 0.86 and 8.2.8,
and both fail on both versions when the guard is disabled.

Recorded here rather than shrugged off, because the pattern is the one this file
keeps naming. A test written against one version of a dependency, asserting a
property that version happens to produce, is the same defect as a test that pins
a buggy value -- and the only reason it surfaced is that CI runs a matrix and a
local gate runs one interpreter.

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

**Round thirty-five.** No measurement changes and no exit code moves; every fix is
naming or wording. Four things a reader or a script might be matching on do change.

`--json`'s `log_expected.status` gains two values it could not previously carry --
`discarded` and `special` -- both drawn from cases that used to report `absent`. A
consumer testing `status == "absent"` to mean "the log is gone" now sees
`"discarded"` for a job that wrote to `/dev/null`, which is the distinction the field
was missing rather than a renaming: no existing value changed meaning, and nothing
was removed. The payload's key count and shape are untouched.

On screen, the `log` line reads differently in three of its cases -- a `/dev/null`
path, a path that is present but not a regular file, and every missed log in the
**dashboard**, which previously said only "none found" and now says what `--plain`
says. Anything grepping for `moved or deleted` on a `/dev/null` job will stop
matching, which is the point.

Cross-run findings name a workload by its real job name wherever the group covers
exactly one, where they previously printed the folded pattern. A script matching a
finding's evidence on a folded name (`m#_robust_#_v#`) will not match where the group
holds a single name; the overview table has named these groups this way for several
rounds, so the two surfaces now agree rather than either moving independently. Groups
covering more than one name are unaffected.

The `no jobs for ...` message gains ` matching --partition <name>` and ` until <t>`
clauses when those arguments were given. The unfiltered sentence is byte-identical.

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
