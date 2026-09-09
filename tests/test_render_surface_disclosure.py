"""Every public builder in `render.py` says what it is, and single-surface ones say where.

`render.py` exists so the dashboard and `--plain` cannot drift: a fact is spelled
once and both surfaces read that spelling. That only works if a reader can tell a
*deliberate* single-surface builder from one that simply has not been wired up yet
-- and the only place that intent can live is the docstring.

Round fifty-six recorded that each single-surface builder's docstring names its
surface. It did not: nine of the forty-eight public functions had no docstring at
all or named no surface. The claim is now true, and this pins it so.
"""

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"

# Words that count as naming a surface, per side.
REPORT_WORDS = ("plain", "report")
TUI_WORDS = ("dashboard", "tui")


def _public_functions(module="render"):
    tree = ast.parse((SRC / f"{module}.py").read_text())
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def names_used_from_render(source: str, pub: set) -> set:
    """Which of `pub` a surface actually calls, honouring how it imports render.

    The two surfaces import differently -- `tui.py` does ``from . import render``
    and calls ``render.bar``, `report.py` does ``from .render import (...)`` and
    calls ``bar`` bare -- so a resolver has to handle both.

    It must ALSO not count a bare name that merely collides with a builder. A
    first cut of this check counted every ``ast.Name``, and reported `bar_cells`
    as called by the dashboard: `tui.py` has a *local variable* of that name, and
    passes it to `pair_value_budget(width, bar_cells=...)`. Nothing calls the
    builder outside `render.py`. Hence the ``& imported`` guard, which is the
    whole reason this helper is worth its own test below.
    """
    tree = ast.parse(source)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("render")
        for alias in node.names
    }
    used = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "render"
            and node.attr in pub
        ):
            used.add(node.attr)
        if isinstance(node, ast.Name) and node.id in pub & imported:
            used.add(node.id)
    return used


def _classify():
    pub = {n.name for n in _public_functions()}
    report = names_used_from_render((SRC / "report.py").read_text(), pub)
    tui = names_used_from_render((SRC / "tui.py").read_text(), pub)
    return {
        "both": pub & report & tui,
        "report_only": (pub & report) - tui,
        "tui_only": (pub & tui) - report,
        "neither": pub - report - tui,
    }


class TestEveryPublicBuilderIsDocumented:
    def test_none_is_bare(self):
        bare = [n.name for n in _public_functions() if not ast.get_docstring(n)]
        assert bare == [], (
            "public in render.py with no docstring: %s -- this module's job is that "
            "one fact has one spelling, so a builder that explains nothing cannot "
            "be reused with confidence" % bare
        )

    def test_the_count_is_what_the_docs_claim(self):
        # Guards against the check above passing because it found nothing to check.
        assert len(_public_functions()) == 49


class TestSingleSurfaceBuildersNameTheirSurface:
    @pytest.mark.parametrize(
        "bucket,words", [("report_only", REPORT_WORDS), ("tui_only", TUI_WORDS)]
    )
    def test_each_says_where_it_belongs(self, bucket, words):
        docs = {n.name: (ast.get_docstring(n) or "").lower() for n in _public_functions()}
        silent = sorted(
            name for name in _classify()[bucket] if not any(w in docs[name] for w in words)
        )
        assert silent == [], (
            "%s builders naming no surface: %s -- a reader cannot tell a deliberate "
            "split from an unwired one" % (bucket, silent)
        )

    def test_the_classification_is_frozen(self):
        """A builder crossing surfaces should be a decision, not a diff nobody saw."""
        sizes = {k: len(v) for k, v in _classify().items()}
        # 29 -> 30 both: `idle_workload_note` was added and wired to BOTH surfaces
        # deliberately, which is what this test asks a change to declare.
        assert sizes == {"both": 30, "report_only": 5, "tui_only": 8, "neither": 6}


class TestControls:
    """Independent of every docstring in render.py, so they hold in both states."""

    def test_the_resolver_ignores_a_local_variable_collision(self):
        """The trap that made a first cut of this file wrong, pinned on planted source.

        Built from a synthetic module, not from `tui.py`, so it measures the
        resolver rather than today's call graph.
        """
        pub = {"bar_cells", "bar"}
        planted = (
            "from . import render\n"
            "def draw():\n"
            "    bar_cells = 3\n"  # a local, NOT the builder
            "    return render.bar(bar_cells)\n"
        )
        used = names_used_from_render(planted, pub)
        assert used == {"bar"}, used

    def test_the_resolver_sees_both_import_styles(self):
        pub = {"bar", "clip"}
        assert names_used_from_render("from . import render\nx = render.clip('a', 2)\n", pub) == {
            "clip"
        }
        assert names_used_from_render("from .render import bar\ny = bar(1, '')\n", pub) == {"bar"}

    def test_a_bare_from_import_name_is_not_credited_to_the_module_path(self):
        # `report.py`-style import must not require the `render.` prefix, and a
        # name that was never imported must not count however it is spelled.
        assert names_used_from_render("z = severity_tag('FAIL')\n", {"severity_tag"}) == set()
