import pytest

import measure_sample_rate as measure_module
from measure_sample_rate import parse_args, summarize_samples


class FakeHx711:
    def __init__(self, values):
        self.values = iter(values)

    def read_word(self, timeout_seconds=0.5):
        try:
            return next(self.values)
        except StopIteration:
            return None


def test_parse_args_defaults():
    args = parse_args([])

    assert args.gpio == "rpi"
    assert args.seconds == 60.0
    assert args.samples_per_batch == 100
    assert args.glitch_threshold == 1.0
    assert args.glitch_mad_scale == 5.0


@pytest.mark.parametrize(
    "argv",
    [
        ["--seconds", "0"],
        ["--samples-per-batch", "0"],
        ["--glitch-threshold", "-1"],
        ["--glitch-mad-scale", "-1"],
    ],
)
def test_parse_args_rejects_invalid_values(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_summarize_samples_counts_outliers_from_median():
    values = [100, 100, 100, 100, 1000]

    stats = summarize_samples(values, 1.0, 5.0)

    assert stats["sample_count"] == 5
    assert stats["median"] == 100
    assert stats["mad"] == 0
    assert stats["threshold"] == 1.0
    assert stats["glitch_count"] == 1
    assert stats["glitch_total"] == 900
    assert stats["glitch_mean"] == 900
    assert stats["glitch_max"] == 900


def test_summarize_samples_uses_mad_when_noise_is_present():
    values = [98, 99, 100, 100, 101, 200]

    stats = summarize_samples(values, 1.0, 2.0)

    assert stats["threshold"] == 2.0
    assert stats["glitch_count"] == 1
    assert stats["glitch_max"] == 100


def test_summarize_samples_with_no_values():
    assert summarize_samples([], 1.0, 5.0) is None


def test_measure_sample_rate_collects_samples_and_reports_glitches(
    monkeypatch, capsys
):
    times = iter([0.0, 0.0, 0.0, 0.01, 0.01, 0.01, 0.02, 2.0])
    monkeypatch.setattr(measure_module.time, "monotonic", lambda: next(times))
    hx = FakeHx711([100, 100, 1000, 100, 100])

    results = measure_module.measure_sample_rate(hx, 1.0, 3, 1.0, 5.0)
    measure_module.print_summary(results)

    output = capsys.readouterr().out
    assert results["samples"] == [100, 100, 1000, 100, 100]
    assert results["drop_count"] == 1
    assert "Glitches: 1 / 5 (20.00%)" in output
    assert "max magnitude 900" in output
