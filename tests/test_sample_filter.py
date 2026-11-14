import math

import pytest

from hx711.sample_filter import SampleFilter


def test_alpha_uses_exponential_cutoff_mapping():
    sample_frequency_hz = 80.0
    cutoff_frequency_hz = 10.0
    period = 1.0 / sample_frequency_hz
    expected_alpha = 1.0 - math.exp(
        -2.0 * math.pi * cutoff_frequency_hz * period
    )

    sample_filter = SampleFilter(sample_frequency_hz, cutoff_frequency_hz)

    assert sample_filter._alpha == pytest.approx(expected_alpha)


def test_median_filter_rejects_a_single_outlier():
    sample_filter = SampleFilter(80.0, 10.0, median_window=5)

    for _ in range(4):
        assert sample_filter.sample(0.0) == 0.0

    assert sample_filter.sample(100.0) == 0.0


def test_step_response_waits_for_the_median_window_to_fill():
    sample_filter = SampleFilter(80.0, 10.0, median_window=5)

    for _ in range(5):
        assert sample_filter.sample(0.0) == 0.0

    assert sample_filter.sample(100.0) == 0.0
    assert sample_filter.sample(100.0) == 0.0

    output = sample_filter.sample(100.0)

    assert 0.0 < output < 100.0


def test_reset_starts_a_fresh_window():
    sample_filter = SampleFilter(80.0, 10.0, median_window=3)

    for value in (0.0, 50.0, 100.0):
        sample_filter.sample(value)

    sample_filter.reset()

    assert sample_filter.sample(25.0) == 25.0


def test_window_length_is_bounded_by_median_window():
    sample_filter = SampleFilter(80.0, 10.0, median_window=3)

    for value in range(10):
        sample_filter.sample(float(value))

    assert len(sample_filter._rolling_window) == 3


@pytest.mark.parametrize(
    "args",
    [
        (0.0, 10.0),
        (-1.0, 10.0),
        (float("nan"), 10.0),
        (float("inf"), 10.0),
        (80.0, 0.0),
        (80.0, -1.0),
        (80.0, float("nan")),
        (80.0, float("inf")),
    ],
)
def test_invalid_frequencies_raise_value_error(args):
    with pytest.raises(ValueError, match="frequency_hz"):
        SampleFilter(*args)


@pytest.mark.parametrize("median_window", [0, -1, 1.5, 2.0])
def test_invalid_median_window_raises_value_error(median_window):
    with pytest.raises(ValueError, match="median_window"):
        SampleFilter(80.0, 10.0, median_window)
