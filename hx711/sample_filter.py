#! /usr/bin/python3

"""Filters for calibrated HX711 samples.

Every filter implements ``sample(value)`` and ``reset()``, which is the
interface used by ``HX711.set_filter()``.
"""

import math
import statistics
from collections import deque


def _validate_finite_positive(value, name):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("{} must be a finite number > 0".format(name))


def _validate_finite_nonnegative(value, name):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("{} must be a finite number >= 0".format(name))


def _validate_window(window, name):
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("{} must be an integer >= 1".format(name))


def _alpha_for(sample_frequency_hz, cutoff_frequency_hz):
    period = 1.0 / sample_frequency_hz
    return 1.0 - math.exp(-2.0 * math.pi * cutoff_frequency_hz * period)


class NoFilter:
    """Pass samples through unchanged."""

    def reset(self):
        pass

    def sample(self, input_sample):
        return input_sample


class MedianFilter:
    """Return the median of the last ``window`` samples."""

    def __init__(self, window=5):
        _validate_window(window, "window")

        self._window = window
        self._rolling_window = deque(maxlen=window)

    def reset(self):
        self._rolling_window.clear()

    def sample(self, input_sample):
        self._rolling_window.append(input_sample)
        return statistics.median(self._rolling_window)


class ExponentialFilter:
    """First-order low-pass filter using an exponential cutoff mapping."""

    def __init__(self, sample_frequency_hz, cutoff_frequency_hz):
        _validate_finite_positive(sample_frequency_hz, "sample_frequency_hz")
        _validate_finite_positive(cutoff_frequency_hz, "cutoff_frequency_hz")

        self._sample_frequency_hz = sample_frequency_hz
        self._cutoff_frequency_hz = cutoff_frequency_hz
        self._alpha = _alpha_for(sample_frequency_hz, cutoff_frequency_hz)
        self._moving_average = None

    def reset(self):
        self._moving_average = None

    def sample(self, input_sample):
        if self._moving_average is None:
            self._moving_average = input_sample
        else:
            self._moving_average += self._alpha * (
                input_sample - self._moving_average
            )

        return self._moving_average


class MedianExponentialFilter:
    """Median filter followed by an exponential low-pass filter.

    This was originally the only filter and is exported as ``SampleFilter``
    for backwards compatibility.
    """

    def __init__(self, sample_frequency_hz, cutoff_frequency_hz, median_window=5):
        _validate_finite_positive(sample_frequency_hz, "sample_frequency_hz")
        _validate_finite_positive(cutoff_frequency_hz, "cutoff_frequency_hz")
        _validate_window(median_window, "median_window")

        self._sample_frequency_hz = sample_frequency_hz
        self._cutoff_frequency_hz = cutoff_frequency_hz
        self._median_window = median_window
        self._alpha = _alpha_for(sample_frequency_hz, cutoff_frequency_hz)
        self._rolling_window = deque(maxlen=median_window)
        self._moving_average = None

    def reset(self):
        self._rolling_window.clear()
        self._moving_average = None

    def sample(self, input_sample):
        self._rolling_window.append(input_sample)

        # Get median of rolling sample window, to get rid of glitches.
        median = statistics.median(self._rolling_window)

        if self._moving_average is None:
            self._moving_average = median

        # Low pass the deglitched sample.
        self._moving_average *= 1.0 - self._alpha
        self._moving_average += self._alpha * median

        return self._moving_average


class HampelFilter:
    """Replace outliers with the rolling median using median absolute deviation.

    The current sample is included in the window. A sample is replaced when
    its distance from the window median exceeds
    ``max(min_mad, threshold * MAD * mad_scale)``. ``mad_scale`` defaults to
    1.4826 so MAD estimates the standard deviation of normally distributed
    noise.
    """

    def __init__(
        self,
        window=7,
        threshold=3.0,
        min_mad=0.0,
        mad_scale=1.4826,
    ):
        _validate_window(window, "window")
        _validate_finite_nonnegative(threshold, "threshold")
        _validate_finite_nonnegative(min_mad, "min_mad")
        _validate_finite_positive(mad_scale, "mad_scale")

        self._window = window
        self._threshold = threshold
        self._min_mad = min_mad
        self._mad_scale = mad_scale
        self._rolling_window = deque(maxlen=window)

    def reset(self):
        self._rolling_window.clear()

    def sample(self, input_sample):
        self._rolling_window.append(input_sample)

        median = statistics.median(self._rolling_window)
        deviations = [abs(value - median) for value in self._rolling_window]
        mad = statistics.median(deviations) * self._mad_scale
        limit = max(self._min_mad, self._threshold * mad)

        if abs(input_sample - median) > limit:
            return median

        return input_sample


class HampelExponentialFilter:
    """Hampel outlier rejection followed by an exponential low-pass filter."""

    def __init__(
        self,
        sample_frequency_hz,
        cutoff_frequency_hz,
        window=7,
        threshold=3.0,
        min_mad=0.0,
        mad_scale=1.4826,
    ):
        self._exponential = ExponentialFilter(
            sample_frequency_hz, cutoff_frequency_hz
        )
        self._hampel = HampelFilter(
            window=window,
            threshold=threshold,
            min_mad=min_mad,
            mad_scale=mad_scale,
        )

        self._sample_frequency_hz = self._exponential._sample_frequency_hz
        self._cutoff_frequency_hz = self._exponential._cutoff_frequency_hz
        self._alpha = self._exponential._alpha

    def reset(self):
        self._hampel.reset()
        self._exponential.reset()

    def sample(self, input_sample):
        return self._exponential.sample(self._hampel.sample(input_sample))


# Backwards-compatible name for the original median + EMA filter.
SampleFilter = MedianExponentialFilter


__all__ = [
    "NoFilter",
    "MedianFilter",
    "ExponentialFilter",
    "MedianExponentialFilter",
    "HampelFilter",
    "HampelExponentialFilter",
    "SampleFilter",
]


# EOF - sample_filter.py
