import math

import pytest

from hx711 import (
    ExponentialFilter,
    HampelExponentialFilter,
    HampelFilter,
    MedianExponentialFilter,
    MedianFilter,
    NoFilter,
)
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


def test_sample_filter_is_backwards_compatible_alias():
    assert SampleFilter is MedianExponentialFilter


def test_no_filter_passes_samples_through():
    sample_filter = NoFilter()

    assert sample_filter.sample(1.5) == 1.5
    assert sample_filter.sample(-2.0) == -2.0

    sample_filter.reset()

    assert sample_filter.sample(3.0) == 3.0


def test_pure_median_filter_rejects_a_spike():
    sample_filter = MedianFilter(window=5)

    for _ in range(4):
        assert sample_filter.sample(10.0) == 10.0

    assert sample_filter.sample(1000.0) == 10.0


def test_pure_median_filter_reset_clears_state():
    sample_filter = MedianFilter(window=3)

    for value in (10.0, 20.0, 30.0):
        sample_filter.sample(value)

    sample_filter.reset()

    assert sample_filter.sample(7.0) == 7.0


def test_exponential_filter_smooths_without_a_median_stage():
    sample_filter = ExponentialFilter(80.0, 10.0)
    expected_alpha = 1.0 - math.exp(-2.0 * math.pi * 10.0 / 80.0)

    assert sample_filter._alpha == pytest.approx(expected_alpha)
    assert sample_filter.sample(10.0) == 10.0

    output = sample_filter.sample(20.0)

    assert 10.0 < output < 20.0
    assert output == pytest.approx(10.0 + expected_alpha * 10.0)


def test_exponential_filter_reset_clears_state():
    sample_filter = ExponentialFilter(80.0, 10.0)

    for value in (0.0, 100.0):
        sample_filter.sample(value)

    sample_filter.reset()

    assert sample_filter.sample(25.0) == 25.0


def test_hampel_filter_replaces_a_spike_with_the_window_median():
    sample_filter = HampelFilter(window=7, threshold=3.0)

    for _ in range(6):
        assert sample_filter.sample(10.0) == 10.0

    assert sample_filter.sample(1000.0) == 10.0


def test_hampel_filter_keeps_samples_within_the_mad_limit():
    sample_filter = HampelFilter(window=7, threshold=3.0)

    for value in (10.0, 10.1, 9.9, 10.0, 10.2, 9.8):
        sample_filter.sample(value)

    assert sample_filter.sample(10.1) == 10.1


def test_hampel_min_mad_avoids_rejecting_small_changes_when_mad_is_zero():
    sample_filter = HampelFilter(window=7, threshold=3.0, min_mad=2.0)

    for _ in range(6):
        sample_filter.sample(10.0)

    assert sample_filter.sample(11.0) == 11.0


def test_hampel_filter_reset_clears_state():
    sample_filter = HampelFilter(window=7)

    for value in (10.0, 10.0, 10.0, 1000.0):
        sample_filter.sample(value)

    sample_filter.reset()

    assert sample_filter.sample(5.0) == 5.0


def test_hampel_exponential_filter_rejects_spikes_before_smoothing():
    sample_filter = HampelExponentialFilter(80.0, 10.0, window=7)

    for _ in range(6):
        assert sample_filter.sample(10.0) == 10.0

    assert sample_filter.sample(1000.0) == 10.0
    sample_filter.reset()
    assert sample_filter.sample(1000.0) == 1000.0


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"window": 0}, "window"),
        ({"threshold": -1.0}, "threshold"),
        ({"min_mad": -1.0}, "min_mad"),
        ({"mad_scale": 0.0}, "mad_scale"),
        ({"mad_scale": float("nan")}, "mad_scale"),
    ],
)
def test_invalid_hampel_parameters_raise_value_error(kwargs, expected):
    with pytest.raises(ValueError, match=expected):
        HampelFilter(**kwargs)


@pytest.mark.parametrize(
    "args, expected",
    [
        ((0.0, 10.0), "sample_frequency_hz"),
        ((80.0, 0.0), "cutoff_frequency_hz"),
    ],
)
def test_invalid_exponential_frequencies_raise_value_error(args, expected):
    with pytest.raises(ValueError, match=expected):
        ExponentialFilter(*args)
