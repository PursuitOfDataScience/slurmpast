"""The command line: argument handling, exit codes, and the JSON contract.

`--demo` carries these tests, because it is the one path that needs no scheduler
-- the same reason CI can run them on a runner with no Slurm installed.
"""

import json

import pytest

from slurmpast import cli
from slurmpast.sacct import SacctError


def run(*argv):
    return cli.main(list(argv))


class TestRelativeTimeSpecs:
    """sacct rejects a bare `-7days` outright, but it is the obvious thing to
    type and argparse would meanwhile read it as an unknown option."""

    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("-7days", "now-7days"),
            ("-1day", "now-1day"),
            ("- 3 weeks", "now-3weeks"),
            ("now-7days", "now-7days"),
            ("2026-01-01", "2026-01-01"),
            ("", ""),
        ],
    )
    def test_normalize(self, spec, expected):
        assert cli.normalize_time_spec(spec) == expected

    def test_none_is_left_alone(self):
        assert cli.normalize_time_spec(None) is None

    @pytest.mark.parametrize("flag", ["-S", "--since", "-E", "--until"])
    def test_a_leading_dash_value_is_glued_to_its_flag(self, flag):
        assert cli._glue_negative_values([flag, "-7days"]) == ["%s=-7days" % flag]

    def test_a_long_option_is_not_swallowed_as_a_value(self):
        assert cli._glue_negative_values(["-S", "--plain"]) == ["-S", "--plain"]

    def test_the_glued_form_survives_argparse_and_is_rewritten(self):
        argv = cli._glue_negative_values(["-S", "-7days", "--overview"])
        args = cli.build_parser().parse_args(argv)
        assert cli.normalize_time_spec(args.since) == "now-7days"

    def test_a_trailing_flag_with_no_value_does_not_crash(self):
        assert cli._glue_negative_values(["-S"]) == ["-S"]


class TestExitCodes:
    """The exit status is the only thing a script can read, so it has to mean
    something: 2 could not answer, 1 answered and it is bad, 0 answered."""

    def test_unreachable_sacct_is_a_clean_two(self, monkeypatch, capsys):
        def boom(*_a, **_kw):
            raise SacctError("cannot execute sacct: No such file or directory")

        monkeypatch.setattr(cli.Sacct, "history", boom)
        assert run("--overview", "--plain", "--no-color") == 2
        assert "slurmpast:" in capsys.readouterr().err

    def test_no_traceback_leaks_on_that_path(self, monkeypatch, capsys):
        def boom(*_a, **_kw):
            raise SacctError("nope")

        monkeypatch.setattr(cli.Sacct, "history", boom)
        run("--overview", "--plain", "--no-color")
        assert "Traceback" not in capsys.readouterr().err

    def test_critical_cross_run_findings_exit_one(self, capsys):
        """The demo history contains a workload that failed 18 of 20 runs."""
        assert run("--demo", "--plain", "--no-color") == 1
        assert capsys.readouterr().out

    def test_a_view_that_only_reports_exits_zero(self, capsys):
        assert run("--demo", "--overview", "--plain", "--no-color") == 0
        assert "JOB NAME" in capsys.readouterr().out


class TestTextViews:
    @pytest.mark.parametrize("view", ["--overview", "--patterns", "--nodes", "--sizing"])
    def test_every_view_renders_without_a_scheduler(self, view, capsys):
        assert run("--demo", view, "--no-color") == 0
        assert capsys.readouterr().out.strip()

    def test_the_window_is_named_as_synthetic_in_demo_mode(self, capsys):
        run("--demo", "--overview", "--plain", "--no-color")
        assert "synthetic demo data" in capsys.readouterr().out

    def test_no_machine_time_syntax_reaches_the_output(self, capsys):
        """Not "now-7days" -- the reader should not have to parse the tool's own
        arguments back out of its output."""
        run("--demo", "--overview", "--plain", "--no-color")
        assert "now-" not in capsys.readouterr().out


class TestJobIds:
    def test_an_explicit_id_selects_only_that_job(self, capsys):
        assert run("--demo", "5100057", "--no-color") in (0, 1)
        out = capsys.readouterr().out
        assert "5100057" in out
        assert "5100056" not in out

    def test_an_unknown_id_is_a_clean_error(self, capsys):
        assert run("--demo", "999999999", "--no-color") == 2
        assert "no demo job matches" in capsys.readouterr().err


class TestJsonPayload:
    def _payload(self, capsys, *argv):
        run("--demo", "--json", "--no-color", *argv)
        return json.loads(capsys.readouterr().out)

    def test_job_payload_is_valid_json_with_a_version(self, capsys):
        payload = self._payload(capsys, "5100056")
        assert payload["slurmpast"]
        assert payload["jobs"]

    def test_unread_values_are_null_never_zero(self, capsys):
        """A fabricated 0 is indistinguishable from a real measurement."""
        job = self._payload(capsys, "5100057")["jobs"][0]
        assert job["gpu"]["utilization"] is None
        assert job["energy_joules"] is None

    def test_cores_and_memory_both_reach_the_payload(self, capsys):
        job = self._payload(capsys, "5100056")["jobs"][0]
        assert job["cpu"]["utilization"] is not None
        assert job["memory"]["peak_bytes"] is not None

    @pytest.mark.parametrize("view", ["--overview", "--patterns", "--nodes", "--sizing"])
    def test_every_view_has_a_json_form(self, capsys, view):
        run("--demo", "--json", "--no-color", view)
        assert json.loads(capsys.readouterr().out)["slurmpast"]


class TestParser:
    def test_version_is_advertised(self, capsys):
        with pytest.raises(SystemExit) as exc:
            run("--version")
        assert exc.value.code == 0
        assert "slurmpast" in capsys.readouterr().out

    def test_the_epilog_examples_use_flags_that_exist(self):
        parser = cli.build_parser()
        known = {option for action in parser._actions for option in action.option_strings}
        for line in cli.EPILOG.splitlines():
            for token in line.split():
                if token.startswith("--"):
                    assert token in known, token


class TestJsonReportsSeverityInItsExitCode:
    """`--json` is the mode a script checks `$?` from, and it always returned 0.

    The same query rendered as text exited 1. (`--overview`/`--patterns`/`--nodes`/
    `--sizing` do always exit 0, deliberately -- they report rather than judge.
    This path judges.)
    """

    def test_json_and_text_agree_on_the_default_view(self, capsys):
        text = run("--demo", "--plain", "--no-color")
        capsys.readouterr()
        as_json = run("--demo", "--json", "--no-color")
        capsys.readouterr()
        assert as_json == text

    def test_the_findings_behind_the_code_are_in_the_payload(self, capsys):
        run("--demo", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert "patterns" in payload, "the exit code rests on these"
        assert any(f["severity"] == "critical" for f in payload["patterns"])

    def test_explicit_ids_report_their_own_findings(self, capsys):
        """With ids given, per-job verdicts decide it -- as in the text path."""
        healthy = run("--demo", "--json", "--no-color", "5100021")
        capsys.readouterr()
        assert healthy in (0, 1)


class TestAMissingValueIsAnError:
    """`-u -p gpu` -- what `-u "$USER" -p gpu` becomes when $USER is unset.

    The negative-value glue took `-p` as the value of `-u`, leaving `gpu` as a job
    id and the partition filter silently gone. The error then named a job the user
    never typed.
    """

    def test_a_known_flag_is_not_swallowed_as_a_value(self):
        assert cli._glue_negative_values(["-u", "-p", "gpu"]) == ["-u", "-p", "gpu"]

    def test_argparse_gets_to_complain(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            run("--demo", "-u", "-p", "gpu", "--no-color")
        assert exit_info.value.code == 2
        assert "expected one argument" in capsys.readouterr().err

    def test_a_real_relative_time_still_glues(self):
        assert cli._glue_negative_values(["-S", "-7days"]) == ["-S=-7days"]

    def test_a_dash_leading_username_still_glues(self):
        assert cli._glue_negative_values(["-u", "-odd-name"]) == ["-u=-odd-name"]


class TestDemoHonoursFailed:
    """`--help` says "only jobs that failed"; the demo returned all 58.

    The real path narrows the whole history through sacct's `--state`, so the demo
    has to narrow the whole history too -- not just the list at the bottom.
    """

    def test_the_summary_shrinks(self, capsys):
        run("--demo", "--overview", "--json", "--no-color")
        everything = json.loads(capsys.readouterr().out)["summary"]["jobs"]
        run("--demo", "--failed", "--overview", "--json", "--no-color")
        only_failed = json.loads(capsys.readouterr().out)["summary"]["jobs"]
        assert 0 < only_failed < everything

    def test_what_is_left_really_did_fail(self, capsys):
        run("--demo", "--failed", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert payload["jobs"]
        assert all(j["outcome"]["failed"] for j in payload["jobs"])


class TestTheDemoStaysSynthetic:
    """A synthetic job wrote no log, so anything a log search turns up is a real
    file belonging to a real run on this machine -- and its text feeds `diagnose`.
    Measured before the fix: 39 of the 58 demo jobs were handed a file out of the
    user's own work directory, four of them gaining findings (`nccl`,
    `import-error`) read out of somebody else's training run. It also made `--demo`
    machine-dependent again, which is what `demo.DEMO_SITE` exists to prevent.
    """

    def test_no_log_is_ever_attached(self, capsys, tmp_path, monkeypatch):
        decoy = tmp_path / "slurm-5100002.out"
        decoy.write_text(
            "Traceback (most recent call last):\n"
            "  File 'train.py', line 1\n"
            "torch.cuda.OutOfMemoryError: CUDA out of memory\n"
        )
        monkeypatch.chdir(tmp_path)
        run("--demo", "5100002", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert payload["jobs"][0]["log"] is None
        codes = {f["code"] for f in payload["jobs"][0]["findings"]}
        assert not codes & {"cuda-oom", "traceback", "import-error", "nccl"}

    def test_the_whole_demo_history_reads_no_logs(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run("--demo", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert payload["jobs"]
        assert all(job["log"] is None for job in payload["jobs"])


class TestTheDemoHonoursEveryNarrowingFlag:
    """`--failed` was fixed on its own once, because ignoring it "made `--help`'s
    'only jobs that failed' false in exactly the place someone tries the flag
    first". `-p` and `-u` sat in the same position and were not. Every synthetic job
    is partition `test`, user `youzhi`, so both should match nothing.
    """

    @pytest.mark.parametrize("argv", [("-p", "gpu"), ("-u", "nobody")])
    def test_a_filter_that_matches_nothing_says_so(self, argv, capsys):
        assert run("--demo", *argv, "--overview", "--no-color") == 2
        assert "no demo jobs match" in capsys.readouterr().err

    @pytest.mark.parametrize("argv", [("-p", "test"), ("-u", "youzhi")])
    def test_a_filter_that_matches_everything_changes_nothing(self, argv, capsys):
        run("--demo", "--overview", "--json", "--no-color")
        everything = json.loads(capsys.readouterr().out)["summary"]["jobs"]
        run("--demo", *argv, "--overview", "--json", "--no-color")
        assert json.loads(capsys.readouterr().out)["summary"]["jobs"] == everything

    def test_an_explicit_job_id_still_ignores_the_filters(self, capsys):
        """Matching the real path, where `-j` goes straight to sacct and the window
        and filters do not apply either. (Exit 1, not 2: the job is found and has a
        critical finding, which is what `--json` reports through `$?`.)"""
        assert run("--demo", "5100001", "-p", "gpu", "--json", "--no-color") != 2
        assert json.loads(capsys.readouterr().out)["jobs"][0]["identity"]["job_id"] == "5100001"


class TestWhoTheQueryIsAbout:
    """`_load` collapsed the scope with `args.user or getpass.getuser()`, which made
    `Sacct.history`'s `--allusers` branch unreachable from the CLI -- and there was
    no flag for it either, while `patterns.group_key` documented a multi-user query
    as "one flag away".
    """

    class _Recorder:
        """Stands in for Sacct: records the kwargs and reports an empty window,
        which `_load` turns into the SacctError carrying the scope it asked about."""

        def __init__(self):
            self.kwargs = None

        def history(self, **kwargs):
            self.kwargs = kwargs
            return []

    def _scope(self, *argv):
        sacct = self._Recorder()
        args = cli.build_parser().parse_args(list(argv))
        with pytest.raises(SacctError) as caught:
            cli._load(args, sacct)
        return sacct.kwargs, str(caught.value)

    def test_all_users_reaches_the_allusers_branch(self):
        kwargs, message = self._scope("--all-users")
        assert kwargs["all_users"] is True
        assert kwargs["user"] is None
        assert "any user" in message

    def test_a_named_user_is_queried_and_named_back(self):
        kwargs, message = self._scope("-u", "alice")
        assert kwargs["all_users"] is False
        assert kwargs["user"] == "alice"
        # A site with PrivateData=jobs answers with an empty set and no error, so
        # this line is the only thing telling the reader whose window came back.
        assert "no jobs for alice" in message

    def test_a_list_of_users_is_handed_to_sacct_whole(self):
        kwargs, _ = self._scope("-u", "alice,bob")
        assert kwargs["user"] == "alice,bob"

    def test_no_flag_still_means_me(self):
        import getpass

        kwargs, _ = self._scope()
        assert kwargs["user"] == getpass.getuser()
        assert kwargs["all_users"] is False

    def test_the_two_flags_contradict_rather_than_one_winning_silently(self, capsys):
        with pytest.raises(SystemExit) as caught:
            run("--all-users", "-u", "alice")
        assert caught.value.code == 2
        assert "pick one" in capsys.readouterr().err

    def test_the_demo_offers_the_flag_too(self, capsys):
        """Every synthetic job is user `youzhi`, so --all-users must not narrow."""
        run("--demo", "--overview", "--json", "--no-color")
        everything = json.loads(capsys.readouterr().out)["summary"]["jobs"]
        run("--demo", "--all-users", "--overview", "--json", "--no-color")
        assert json.loads(capsys.readouterr().out)["summary"]["jobs"] == everything


class TestSizingHonoursTheSort:
    """`--sort` is documented as "workload ordering" with no exception, and
    `--sizing` is a workload-ordered, truncated list -- whose own note says "the
    workload most worth re-sizing can sit at position 13". `--sort rate` is the
    remedy for exactly that, and both the text and the JSON discarded it."""

    def test_the_json_order_follows_the_flag(self, capsys):
        run("--demo", "--sizing", "--json", "--no-color")
        by_cost = [w["name"] for w in json.loads(capsys.readouterr().out)["workloads"]]
        run("--demo", "--sizing", "--json", "--sort", "name", "--no-color")
        by_name = [w["name"] for w in json.loads(capsys.readouterr().out)["workloads"]]
        assert by_name == sorted(by_name)
        assert by_name != by_cost

    def test_the_text_order_follows_the_flag(self, capsys):
        run("--demo", "--sizing", "--no-color")
        by_cost = capsys.readouterr().out
        run("--demo", "--sizing", "--sort", "rate", "--no-color")
        by_rate = capsys.readouterr().out
        assert by_cost != by_rate

    def test_a_non_default_order_is_named_on_screen(self, capsys):
        run("--demo", "--sizing", "--sort", "rate", "--no-color")
        assert "ordered by failure rate" in capsys.readouterr().out
        run("--demo", "--sizing", "--no-color")
        assert "ordered by" not in capsys.readouterr().out


class TestExplicitIdsAreNotTruncated:
    """`--limit` is documented as "rows in plain output". Ids the caller typed out
    are not rows the tool chose to show them, and `-n` defaults to 25, so a query
    naming 30 jobs printed 25 post-mortems and said nothing about the other five.
    """

    IDS = [str(5100001 + i) for i in range(30)]

    def test_every_id_asked_for_is_answered(self, capsys):
        run("--demo", "--plain", "--no-color", *self.IDS)
        out = capsys.readouterr().out
        missing = [j for j in self.IDS if "job %s" % j not in out]
        assert not missing, missing

    def test_the_json_array_is_not_short(self, capsys):
        run("--demo", "--json", "--no-color", *self.IDS)
        payload = json.loads(capsys.readouterr().out)
        assert [j["identity"]["job_id"] for j in payload["jobs"]] == self.IDS

    def test_a_finding_past_the_limit_still_reaches_the_exit_code(self):
        """What the truncation actually cost. The exit code is computed only over
        the jobs examined, so with the tail dropped a CRITICAL on ids 26-30 could
        not reach it: 26 healthy ids and one OUT_OF_MEMORY exited 0."""
        healthy = [str(5100021 + i) for i in range(14)]  # the midtrain runs
        assert run("--demo", "--plain", "--no-color", *healthy) == 0, "control"
        oom = "5100036"  # OUT_OF_MEMORY, rc-tok-github_code
        padded = healthy + [str(5100021 + i) for i in range(14)] + [oom]
        assert len(padded) > 25, "the tail has to fall past the default -n"
        assert run("--demo", "--plain", "--no-color", *padded) == 1

    def test_the_list_branch_still_truncates(self, capsys):
        """The control the other way: `-n` is unchanged where it means something."""
        run("--demo", "--plain", "--no-color", "-n", "5")
        assert "more (raise --limit)" in capsys.readouterr().out


class TestNoLogsClaimsNothingAboutTheFilesystem:
    """Under `--no-logs` nothing is stat'd, so "none found" reported a search that
    never ran -- and with a recorded StdOut the invented claim got stronger and was
    simply false. `--demo` forces `--no-logs`, so every synthetic post-mortem
    shipped one. `tui.JobScreen` has guarded the identical line all along."""

    def test_the_demo_does_not_report_a_search_it_did_not_run(self, capsys):
        run("--demo", "--plain", "--no-color", "5100003")
        out = capsys.readouterr().out
        assert "none found" not in out
        assert "moved or deleted" not in out

    def test_a_recorded_path_is_not_declared_missing(self):
        from slurmpast.model import Job
        from slurmpast.report import Style, render_job

        job = Job(
            job_id="884411",
            name="sft",
            state="FAILED",
            std_out="/scratch/dana/logs/sft-884411.out",
            elapsed=60.0,
        )
        text, _ = render_job(job, style=Style(enabled=False), no_logs=True)
        assert "moved or deleted" not in text
        # The control: asked to look, it says what it found.
        text, _ = render_job(job, style=Style(enabled=False), no_logs=False)
        assert "moved or deleted" in text


class TestTheDemosClockAgreesWithItsJobIds:
    """Slurm hands out job ids in submission order, so a demo whose clock
    disagrees with its ids is a demo of something Slurm cannot produce.

    The stamp was `"0%d:00:00" % (jid % 9)`, which wrapped every ninth job. The
    ten runs of `rc-tok-github_code` all carry `day=20`, so they listed 08:00,
    07:00, 06:00, 05:00, 05:00 -- the narrative backwards, with two runs sharing a
    timestamp -- and it fed a wrong number as well as a wrong order: `sizing._latest`
    picked 5100038 (17G) as the last submission instead of 5100044 (32G).
    """

    @staticmethod
    def _jobs():
        from slurmpast.demo import history

        return history()

    def test_start_order_matches_id_order_within_a_day(self):
        by_day: dict[str, list] = {}
        for job in self._jobs():
            by_day.setdefault(job.start[:10], []).append(job)
        for day, jobs in by_day.items():
            jobs.sort(key=lambda j: int(j.job_id))
            stamps = [j.start for j in jobs]
            assert stamps == sorted(stamps), (day, stamps)

    def test_no_two_runs_of_a_workload_share_a_start(self):
        seen: dict[tuple, str] = {}
        for job in self._jobs():
            key = (job.name, job.start)
            assert key not in seen, "%s and %s both start %s" % (
                seen[key],
                job.job_id,
                job.start,
            )
            seen[key] = job.job_id

    def test_no_series_runs_past_midnight_into_the_next_day(self):
        """The spacing has to keep a day's worth of submissions inside that day,
        or the wrap comes back in a different form."""
        for job in self._jobs():
            assert job.start[11:] < "24:00:00", job.start

    def test_the_sizing_screen_quotes_the_last_request(self, capsys):
        """What the scrambled clock actually cost: the demo advised against a
        ceiling five submissions old."""
        run("--demo", "--sizing", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        workload = next(w for w in payload["workloads"] if w["name"] == "rc-tok-github_code")
        mem = next(a for a in workload["advice"] if a["flag"] == "--mem")
        assert mem["requested"] == "32.0 GiB", mem


class TestTheDemoContainsTheShapesItAdvertises:
    """`demo.tape` sells the synthetic history as containing "a workload that
    hangs and times out at an unchanged --time, a --mem hand-search that ends by
    succeeding at a value that already OOM'd, healthy training runs that correctly
    draw no findings, and one node that eats jobs."

    The last of those was not true. The hang was spread evenly across two nodes
    (12/13 against 6/7), so with the workload held fixed -- the only comparison
    `--nodes` makes -- the demo's own nodes screen said "no node is worse than the
    rest; nothing to exclude", on the screen README leads its "Failure, across
    runs" section with.
    """

    def test_the_nodes_screen_names_a_bad_node(self, capsys):
        run("--demo", "--nodes", "--no-color")
        out = capsys.readouterr().out
        assert "#SBATCH --exclude=" in out, out
        assert "nothing to exclude" not in out

    def test_it_does_so_with_the_workload_control_on(self, capsys):
        """The control that matters. Uncontrolled, the tool labels the table
        "UNCONTROLLED — mixes workloads; a node that hosted one bad campaign will
        look cursed" -- a finding it disclaims is not a demo of the feature."""
        run("--demo", "--nodes", "--no-color")
        out = capsys.readouterr().out
        assert "controlled for workload" in out
        assert "UNCONTROLLED" not in out

    def test_the_workload_still_hangs(self, capsys):
        """And the other advertised shapes survive the redistribution."""
        run("--demo", "--patterns", "--json", "--no-color")
        codes = {f["code"] for f in json.loads(capsys.readouterr().out)["findings"]}
        assert "repeat-failure" in codes
        assert "memory-search" in codes

    def test_the_healthy_workload_still_draws_no_findings(self, capsys):
        assert run("--demo", "--plain", "--no-color", "5100021") == 0
        assert "nothing to flag" in capsys.readouterr().out


class TestAsciiIsHonouredByEveryTextView:
    """`--ascii` was accepted and thrown away by five of the six plain views.

    `cli` passed `ascii_mode` to `render_job` and to `tui.run` and to nothing else,
    so `--ascii --overview` and `--overview` were byte-identical -- round five's
    "#7 & 8. Two flags that were accepted and thrown away", on a third flag. And in
    the one view that did receive it, the flag only ever reached the bar and the
    health dot, so a terminal that could not draw `●` got the fallback for that and
    an em dash and a middle dot anyway.
    """

    VIEWS = ["--plain", "--overview", "--patterns", "--nodes", "--sizing"]

    @pytest.mark.parametrize("view", [*VIEWS, "5100019", "5100056"])
    def test_the_output_is_pure_ascii(self, view, capsys):
        run("--demo", "--ascii", "--no-color", view)
        out = capsys.readouterr().out
        assert out.strip(), "the view should have rendered something"
        offenders = sorted({ch for ch in out if ord(ch) > 127})
        assert not offenders, "%s leaked %r under --ascii" % (view, offenders)

    @pytest.mark.parametrize("view", [*VIEWS, "5100019"])
    def test_the_flag_changes_exactly_the_views_that_had_something_to_fold(self, view, capsys):
        """The control that matters most here: a fold applied to nothing would
        satisfy the test above on any view that is ASCII already.

        Stated as an equivalence rather than a flat "it changed", because
        `--patterns` on the demo history genuinely holds no foldable character and
        asserting a difference there would pin the fixture, not the flag."""
        run("--demo", "--no-color", view)
        plain = capsys.readouterr().out
        run("--demo", "--ascii", "--no-color", view)
        folded = capsys.readouterr().out
        had_unicode = any(ord(ch) > 127 for ch in plain)
        assert (plain != folded) == had_unicode, view

    def test_at_least_one_view_is_genuinely_folded(self, capsys):
        """And the fixture does exercise the fold somewhere, so the equivalence
        above cannot be satisfied by a flag that does nothing at all."""
        changed = []
        for view in self.VIEWS:
            run("--demo", "--no-color", view)
            plain = capsys.readouterr().out
            run("--demo", "--ascii", "--no-color", view)
            if plain != capsys.readouterr().out:
                changed.append(view)
        assert changed, "no demo view exercises the fold"

    @pytest.mark.parametrize("view", [*VIEWS, "5100019"])
    def test_folding_does_not_change_any_line_width(self, view, capsys):
        """Every substitution is one cell for one cell, deliberately: the fold runs
        after wrapping and after `clip` has reserved its marker cell, so a
        two-character replacement would push a fitted row back over the width it
        was just measured to."""
        run("--demo", "--no-color", view)
        plain = capsys.readouterr().out.splitlines()
        run("--demo", "--ascii", "--no-color", view)
        folded = capsys.readouterr().out.splitlines()
        assert len(plain) == len(folded)
        for before, after in zip(plain, folded, strict=True):
            assert len(before) == len(after), (before, after)

    def test_the_help_says_what_the_flag_can_promise(self):
        """Not "instead of Unicode" flatly: Textual draws the dashboard's frame in
        box characters whatever this flag says, so only the piped surface can
        actually come out ASCII."""
        text = cli.build_parser().format_help()
        # The options section, not the usage line, where every flag also appears.
        entry = text.split("--ascii", 2)[-1]
        assert "text output" in entry[:140], entry[:140]


class TestTwoSectionsAreBothPrinted:
    """Asking for two report sections used to yield one, silently.

    Each section branch in `cli.main` ended in `return 0`, so the first one whose
    flag was set won and the rest evaporated with no message and rc=0. Which one
    survived was the order the branches happened to be written in, which no reader
    can see:

        --overview --patterns  -> patterns only
        --overview --nodes     -> nodes only
        --patterns --nodes     -> nodes only
        --overview --sizing    -> sizing only

    Both sibling packages reject this class of mistake loudly and name both flags
    (`slurmwatch: ERROR: --once and --log are mutually exclusive`), which is the
    standard the report holds this one to. Composing is the better answer where
    the reports can coexist, and these can: the default plain output already
    prints several sections in sequence, so asking for two by name has an obvious
    meaning.
    """

    def test_both_sections_appear(self, capsys):
        run("--demo", "--overview", "--patterns", "--plain", "--no-color")
        out = capsys.readouterr().out
        assert "cross-run patterns" in out
        assert "JOB NAME" in out, "the overview table is the part that used to vanish"

    def test_the_order_is_the_reading_order_not_the_branch_order(self, capsys):
        """`--patterns --nodes` used to give nodes, because nodes is written
        first. The composed order is fixed and independent of that."""
        run("--demo", "--patterns", "--nodes", "--plain", "--no-color")
        out = capsys.readouterr().out
        assert out.index("cross-run patterns") < out.index("node reliability")

    def test_the_same_order_however_the_flags_are_typed(self, capsys):
        run("--demo", "--nodes", "--patterns", "--plain", "--no-color")
        first = capsys.readouterr().out
        run("--demo", "--patterns", "--nodes", "--plain", "--no-color")
        assert first == capsys.readouterr().out

    def test_one_section_alone_is_unchanged(self, capsys):
        """The control. Composing must not add a separator, a heading or a blank
        line to the single-section case, which is every existing caller."""
        run("--demo", "--patterns", "--plain", "--no-color")
        out = capsys.readouterr().out
        assert out.startswith("cross-run patterns")
        assert "JOB NAME" not in out


class TestJsonTakesOneSectionAtATime:
    """`--json` emits one document per section and there is no defined way to
    concatenate two, so the composing above is text-only and the pair is refused.

    Refused rather than silently reduced to one, which is the behaviour being
    fixed: picking a winner is exactly what made the text case wrong.
    """

    def test_two_sections_with_json_is_an_error(self, capsys):
        with pytest.raises(SystemExit) as caught:
            run("--demo", "--overview", "--patterns", "--json")
        assert caught.value.code == 2
        err = capsys.readouterr().err
        assert "--overview" in err and "--patterns" in err, err
        assert "one section at a time" in err

    def test_one_section_with_json_emits_exactly_one_document(self, capsys):
        """The control, and the regression this fix nearly shipped.

        Removing the `return 0` that made the sections exclusive also removed the
        one the *json* path relied on, so `--overview --json` printed its document
        and then fell through and printed the per-job payload after it. Valid JSON
        followed by more valid JSON is not valid JSON, and `json.loads` is the
        only thing that says so -- eyeballing the output does not.
        """
        run("--demo", "--overview", "--json", "--no-color")
        json.loads(capsys.readouterr().out)

    def test_json_with_no_section_is_still_one_document(self, capsys):
        run("--demo", "--json", "--no-color")
        json.loads(capsys.readouterr().out)


class TestStepsNeedsAJobToStep:
    """`--steps` is per-job accounting -- `--help` says "on a named job" -- and
    without one it used to evaporate: rc=0, the ordinary overview, and no hint
    that the flag did nothing.
    """

    def test_it_is_refused_and_says_what_to_do(self, capsys):
        with pytest.raises(SystemExit) as caught:
            run("--demo", "--steps", "--plain")
        assert caught.value.code == 2
        err = capsys.readouterr().err
        assert "--steps" in err and "job id" in err, err

    def test_with_a_job_id_it_still_breaks_the_job_down(self, capsys):
        """The control: refusing the bare flag must not cost the flag itself."""
        assert run("--demo", "5100057", "--steps", "--plain", "--no-color") in (0, 1)
        assert "step" in capsys.readouterr().out.lower()


class TestTheDemoAsksTheRealClusterNothing:
    """`--demo` is meant to render identically on a login node and a laptop.

    It already pins the synthetic cluster's `scontrol show config`, because
    several messages are worded from `JobAcctGatherType` and without that the demo
    changed by machine. The partition-ceiling clamp added for the unschedulable
    `--cpus-per-task` finding introduced a second such leak and no test caught it:
    `sizing.cpu_advice` learns a partition's node size by running `sinfo`, so
    `--demo --sizing` on a login node asked the *real* cluster how big its `test`
    nodes are.

    Latent rather than visible, which is why it needed looking for: every CPU
    recommendation in the synthetic history is downward or unchanged, and the
    clamp only applies upward, so the output happened to be identical either way.
    A demo that grew one upward recommendation would have started differing by
    machine with nothing to say so.
    """

    def _subprocesses(self, *argv):
        from slurmpast import site

        seen = []
        real = site._run
        site._run = lambda args: seen.append(list(args)) or real(args)
        try:
            run(*argv)
        finally:
            site._run = real
        return seen

    # Every mode, not the two that happened to break. Twice in three rounds a new
    # field reached the scheduler or the filesystem from a path that promises not
    # to -- `--sizing` running `sinfo` under `--demo`, and `--json` stat-ing a log
    # under `--no-logs` -- and both were invisible in the output. Enumerating the
    # modes is what turns that from a thing caught twice by luck into a thing that
    # cannot be added a third time.
    MODES = (
        ("--overview",),
        ("--patterns",),
        ("--nodes",),
        ("--sizing",),
        ("--plain",),
        ("--failed",),
        ("--json",),
        ("--overview", "--json"),
        ("--sizing", "--json"),
        ("5100057",),
        ("5100057", "--json"),
    )

    @pytest.mark.parametrize("mode", MODES, ids=[" ".join(m) for m in MODES])
    def test_no_mode_asks_the_scheduler_anything(self, mode):
        assert self._subprocesses("--demo", *mode, "--no-color") == []

    def test_the_list_of_modes_is_not_stale(self):
        """The guard on the guard. A mode added to the parser and not to `MODES`
        above would be untested and look tested, which is how the two leaks got
        in -- so the parser is asked what it offers rather than a human
        remembering."""
        parser = cli.build_parser()
        offered = {
            option
            for action in parser._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        # The view-selecting flags. Everything else is a modifier (--no-color,
        # -S) or an escape hatch (--demo, --help) and does not select an output.
        views = {"--overview", "--patterns", "--nodes", "--sizing", "--json", "--failed"}
        assert views <= offered, views - offered
        covered = {flag for mode in self.MODES for flag in mode if flag.startswith("--")}
        assert views <= covered, "views with no isolation test: %s" % (views - covered)

    def test_the_ceiling_used_is_the_synthetic_one(self, capsys):
        """Pinned to a real value rather than to "no ceiling", so the demo
        exercises the same code path a cluster does."""
        from slurmpast.demo import DEMO_PARTITIONS

        run("--demo", "--sizing", "--plain", "--no-color")
        capsys.readouterr()
        from slurmpast.site import partition_ceiling

        assert partition_ceiling("test") == DEMO_PARTITIONS["test"]


class TestTheJsonSaysHowMuchItClipped:
    """`-n/--limit` clips the `--json` findings array and nothing in the payload
    said so.

    No wrong number and no crash: the clip is newest-first, the default output is
    a strict prefix of the full list, and the aggregates in `summary` are computed
    over every job rather than the clipped set. The defect is that it is
    *undetectable*. `summary.jobs` counts everything in the window, so
    `len(jobs) < summary.jobs` is the normal state whether anything was dropped or
    not, and there was no `findings_jobs`, `shown` or `truncated` key to compare
    against.

    The consequence is a monitoring consumer polling this payload: as an account
    accumulates more than `-n` findings-bearing jobs in the window, the oldest
    drop off silently and the JSON looks exactly as complete as before.

    Mirror image of the `--sizing` defect fixed one round earlier -- there the
    text view collapsed what the JSON carried in full, here the JSON is the lossy
    one -- and the same cause: a truncation decided at render time with no field
    recording that it happened.
    """

    def _payload(self, capsys, *extra):
        run("--demo", "--json", "--no-color", *extra)
        return json.loads(capsys.readouterr().out)

    def test_json_reports_how_many_findings_jobs_were_clipped(self, capsys):
        """The test the report asks for by name."""
        clipped = self._payload(capsys, "-n", "5")
        assert len(clipped["jobs"]) == 5
        assert clipped["summary"]["findings_jobs_shown"] == 5
        assert clipped["summary"]["findings_jobs"] > 5, clipped["summary"]

    def test_the_two_counts_agree_when_nothing_was_clipped(self, capsys):
        """The control, and the invariant a consumer actually checks: equal means
        complete."""
        whole = self._payload(capsys, "-n", "0")
        summary = whole["summary"]
        assert summary["findings_jobs"] == summary["findings_jobs_shown"]
        assert summary["findings_jobs"] == len(whole["jobs"])

    def test_the_new_counts_are_not_the_window_total(self, capsys):
        """`summary.jobs` is every job in the window and cannot reveal the clip --
        which is exactly why comparing against it told a consumer nothing."""
        whole = self._payload(capsys, "-n", "0")
        assert whole["summary"]["jobs"] > whole["summary"]["findings_jobs"]


class TestZeroMeansUnlimited:
    """`-n 0` exited 2 with an argparse usage dump.

    A sibling tool in this suite already spells "no limit" as `-n 0`, so the same
    flag meant "unlimited" in one and "usage error" in another. It is also the
    escape hatch the JSON clip above needs.

    The old rejection had a recorded reason -- `-n 0` "renders a table with a
    header, no rows, and a footer saying everything was omitted" -- and that
    reason is about `[:0]`, which is a good argument against 0 as a literal count
    and none at all against this meaning. Under it the table renders everything,
    so the objection cannot arise.
    """

    def test_zero_is_accepted_and_means_everything(self, capsys):
        assert run("--demo", "--overview", "--plain", "--no-color", "-n", "0") == 0
        wide = capsys.readouterr().out
        run("--demo", "--overview", "--plain", "--no-color", "-n", "2")
        narrow = capsys.readouterr().out
        assert len(wide) > len(narrow)

    def test_it_does_not_render_an_empty_table(self, capsys):
        """The recorded objection, asserted as the behaviour that answers it."""
        run("--demo", "--overview", "--plain", "--no-color", "-n", "0")
        out = capsys.readouterr().out
        assert "JOB NAME" in out
        assert "more workload" not in out, "nothing should be reported as omitted"

    @pytest.mark.parametrize("mode", ["--overview", "--plain", "--sizing", "--failed"])
    def test_no_view_claims_a_tail_it_did_not_truncate(self, capsys, mode):
        """The general form of the contradiction, swept across every view `-n`
        governs.

        Fixing `tail_summary` closed it on the overview; nothing said the other
        views were clean, and each keeps its own tail line (`render_list`'s
        "… N more (raise --limit)", `render_sizing`'s "below the N shown"). With
        no limit in force none of them may claim anything is below a fold.

        `--nodes` is deliberately absent: its "N nodes below threshold omitted" is
        a *sample* threshold, not a row limit — it is invariant under `-n`, and
        including it here would assert something false.
        """
        run("--demo", mode, "--plain", "--no-color", "-n", "0")
        out = capsys.readouterr().out
        for claim in ("more workload", "more (raise --limit)", "below the"):
            assert claim not in out, "%s claimed a tail under -n 0: %r" % (mode, claim)

    def test_the_nodes_threshold_note_is_not_a_limit_claim(self, capsys):
        """The control for the exclusion above, so it is a measured fact rather
        than an assumption: that line does not move with `-n`."""
        seen = set()
        for limit in ("0", "1", "25"):
            run("--demo", "--nodes", "--plain", "--no-color", "-n", limit)
            out = capsys.readouterr().out
            seen.add("below threshold omitted" in out)
        assert len(seen) == 1, "the nodes note changed with --limit, so it is one"

    def test_a_negative_limit_is_still_refused(self, capsys):
        """The control. `-n -5` is a plausible typo for `-n 5` -- one this tool
        invites by accepting `-S -7days` -- and must not become a silent slice."""
        with pytest.raises(SystemExit) as caught:
            run("--demo", "--overview", "-n", "-5")
        assert caught.value.code == 2
        assert "0 (unlimited) or more" in capsys.readouterr().err


class TestTheExitCodeContractIsStatedAndOptional:
    """The scan mode exits 0 while reporting critical findings, and until now
    nothing said so.

    Deliberate, and the code says why: without job ids the cross-run patterns
    decide the code, so a scan across a cluster does not exit 1 almost always and
    stay useless as a signal. The JSON path computes the per-job verdict anyway --
    the payload needs it -- and then discards it, which is the asymmetry that
    makes `slurmpast --json || alert` silent on exactly the mode anyone would
    automate.

    So: state the contract, and offer the other reading rather than changing the
    default. Reproduced with one OOM job -- a critical per-job finding, too few
    runs for any pattern -- where the same payload gives rc=0 scanning and rc=1
    by job id.
    """

    def _runner(self):
        from tests.conftest import make_text, row
        from tests.test_portability import _FIELDS

        text = make_text(
            row(
                JobID="900001",
                JobName="solo",
                User="u",
                Partition="p",
                State="OUT_OF_MEMORY",
                ExitCode="0:125",
                Submit="2026-08-23T09:00:00",
                Start="2026-08-23T09:00:00",
                End="2026-08-23T09:10:00",
                ElapsedRaw="600",
                ReqMem="1G",
                NCPUS="1",
                AllocCPUS="1",
                NNodes="1",
                AllocTRES="billing=1,cpu=1,mem=1G,node=1",
            ),
            row(
                JobID="900001.batch",
                JobName="batch",
                State="OUT_OF_MEMORY",
                ExitCode="0:125",
                ElapsedRaw="600",
                TotalCPU="00:09:00",
                NCPUS="1",
                AllocCPUS="1",
                MaxRSS="1048576K",
            ),
        ).replace("|", "\x1f")

        def run_sacct(args):
            if "--helpformat" in args:
                return " ".join(_FIELDS)
            if args and args[0] in ("squeue", "scontrol", "sinfo"):
                return ""
            return text

        return run_sacct

    def _rc(self, monkeypatch, capsys, *argv):
        monkeypatch.setattr("slurmpast.sacct._run", self._runner())
        code = run(*argv)
        capsys.readouterr()
        return code

    def test_exit_code_ignores_per_job_criticals_without_job_ids(self, monkeypatch, capsys):
        """Pinning the current contract, which the report asks for by name and
        agrees is defensible."""
        assert self._rc(monkeypatch, capsys, "--json", "--no-color", "-S", "now-1days") == 0

    def test_the_same_job_asked_for_by_id_still_exits_one(self, monkeypatch, capsys):
        """The asymmetry itself: identical payload, different code."""
        assert self._rc(monkeypatch, capsys, "900001", "--json", "--no-color") == 1

    def test_strict_flag_ors_in_per_job_criticals(self, monkeypatch, capsys):
        """The opt-in, also named in the report."""
        assert (
            self._rc(monkeypatch, capsys, "--json", "--strict", "--no-color", "-S", "now-1days")
            == 1
        )

    def test_strict_reaches_the_text_path_too(self, monkeypatch, capsys):
        """The two paths agree without the flag and must agree under it. They
        reach the answer differently -- the text branch never runs the per-job
        loop -- so this is not the same code being exercised twice."""
        assert (
            self._rc(monkeypatch, capsys, "--plain", "--strict", "--no-color", "-S", "now-1days")
            == 1
        )
        assert self._rc(monkeypatch, capsys, "--plain", "--no-color", "-S", "now-1days") == 0

    def test_the_help_states_all_three_codes(self):
        """Undiscoverable is the actual complaint: `2` is in use as well, so the
        real contract is 0/1/2 with a mode-dependent 1, and `--help` said none of
        it."""
        epilog = cli.EPILOG
        assert "exit status:" in epilog
        for code in ("0 ", "1 ", "2 "):
            assert code in epilog
        assert "--strict" in epilog
        assert "report rather than judge" in epilog


class TestTheSyntheticMarkerReachesEverySurface:
    """`--demo` marks its output as synthetic, and the cross-package review named
    that the pattern the other tools should copy: *"the marker sits in a field the
    output always renders, so it cannot scroll away or be dropped by a consumer."*

    It did not. Checking the compliment rather than accepting it found `--json`
    carrying no marker at all — `summary` had no window and the string "synthetic"
    appeared nowhere in the payload — so a machine consumer of `--demo --json`
    could not tell simulated data from real. That is the same defect filed against
    the sibling tool in the same table (*"no in `--once --json`, 3438 bytes of
    telemetry, zero markers"*), and only the overview had been looked at here.

    Fixed by carrying `history.window` into every payload root, which is worth
    having on its own account: a consumer could not previously tell what window a
    payload covered either.
    """

    JSON_VIEWS = ((), ("--overview",), ("--patterns",), ("--nodes",), ("--sizing",), ("5100057",))

    @pytest.mark.parametrize("view", JSON_VIEWS, ids=[" ".join(v) or "jobs" for v in JSON_VIEWS])
    def test_every_json_surface_says_the_data_is_synthetic(self, capsys, view):
        run("--demo", *view, "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert payload.get("window") == "synthetic demo data", sorted(payload)

    def test_a_real_window_is_named_rather_than_blank(self, capsys, monkeypatch):
        """The control, and the reason this is not a demo-only field: the same key
        tells a consumer what period the numbers cover, which nothing did before."""
        from slurmpast.sacct import SAFE_DELIMITER
        from tests.conftest import make_text, row
        from tests.test_portability import _FIELDS

        # `_FIELDS`, not `Sacct().fields`: the latter negotiates against whatever
        # sacct is on the runner's PATH, so on a real cluster the probe answers 80
        # fields while `row()` builds 85 and every row is dropped as shifted.
        fields = _FIELDS
        text = make_text(
            row(
                JobID="700100",
                JobName="w",
                User="u",
                State="COMPLETED",
                Submit="2026-08-23T09:00:00",
                Start="2026-08-23T09:00:00",
                End="2026-08-23T09:10:00",
                ElapsedRaw="600",
                NCPUS="1",
                AllocCPUS="1",
                NNodes="1",
            )
        ).replace("|", SAFE_DELIMITER)

        def fake(args):
            if "--helpformat" in args:
                return " ".join(fields)
            if args and args[0] in ("squeue", "scontrol", "sinfo"):
                return ""
            return text

        monkeypatch.setattr("slurmpast.sacct._run", fake)
        run("-u", "u", "--overview", "--json", "--no-color", "-S", "now-2days")
        payload = json.loads(capsys.readouterr().out)
        assert payload.get("window") == "last 2 days", payload.get("window")
        assert "synthetic" not in json.dumps(payload)
