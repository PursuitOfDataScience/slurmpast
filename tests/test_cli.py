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
