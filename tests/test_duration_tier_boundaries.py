"""Which tier a duration lands in, decided by the value as printed.

``format_bytes`` states the rule in this same module -- the unit is "chosen for
the value as PRINTED, not as stored" -- and keeps ``_ROUNDS_UP_AT`` to enforce it,
because comparing the raw value made anything under 1 GiB print "1024.0 MiB".
``format_duration`` twenty lines above it tested the raw value:

    59.95s  ->  "60.0s"     the boundary, named in the unit below it
    59.99s  ->  "60.0s"
    0.999s  ->  "1.00s"     two decimals, from the tier reserved for
                            values that are not yet a second

Both tiers now test what the reader is shown. The sub-second tier keeps its two
decimals, which the docstring is explicit about: a hung job's evidence is
"0.52s of CPU" and ``00:00:00`` would erase it.
"""

from slurmpast.duration import format_bytes, format_duration


def test_a_tier_is_chosen_for_the_value_as_printed():
    """The three cases that named a boundary in the wrong unit."""
    assert format_duration(59.95) == "00:01:00"
    assert format_duration(59.99) == "00:01:00"
    # rounds to a whole second, so it belongs to the tenths tier, not hundredths
    assert format_duration(0.999) == "1.0s"


def test_control_a_the_sub_second_evidence_the_docstring_names():
    """CONTROL, passing with the change present or absent.

    "0.52s of CPU" is the reading this tier exists for. A fix that promoted
    everything under a second would erase it, which the docstring calls out as
    the thing not to do.
    """
    assert format_duration(0.52) == "0.52s"
    assert format_duration(0) == "0.00s"
    assert format_duration(0.01) == "0.01s"
    assert format_duration(0.994) == "0.99s"


def test_control_b_the_values_just_below_each_boundary_do_not_move():
    """CONTROL, in both states. Only what rounds ACROSS a tier changes.

    59.94 rounds to 59.9 at one decimal and stays in seconds; 0.994 rounds to
    0.99 and stays in hundredths. This is what says the fix moved a boundary
    rather than a tier.
    """
    assert format_duration(59.9) == "59.9s"
    assert format_duration(59.94) == "59.9s"
    assert format_duration(30) == "30.0s"
    assert format_duration(1.0) == "1.0s"


def test_control_c_the_slurm_shaped_output_is_untouched():
    """CONTROL, in both states. The whole point of the format is that
    ``--time=`` accepts it, so every clock-shaped case must be byte-identical."""
    assert format_duration(60) == "00:01:00"
    assert format_duration(3600) == "01:00:00"
    assert format_duration(3661) == "01:01:01"
    assert format_duration(86399) == "23:59:59"
    assert format_duration(86400) == "1-00:00:00"
    assert format_duration(90061) == "1-01:01:01"
    assert format_duration(None) == "n/a"
    assert format_duration(float("inf")) == "n/a"


def test_control_d_format_bytes_already_obeyed_the_rule():
    """CONTROL, in both states, and the reason this is a drift and not a choice.

    The sibling function in this module tests the printed value and has done
    since the round that added ``_ROUNDS_UP_AT``. Asserted here so the two stay
    answerable to one rule rather than each carrying its own.
    """
    assert format_bytes(1024**3 * 1023.96) == "1.0 TiB"
    assert format_bytes(1024**2 * 1023.99) == "1.0 GiB"
    assert format_bytes(1023) == "1023 B"
