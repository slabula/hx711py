#! /usr/bin/python3

import math
import statistics
from collections import deque


class SampleFilter:
    def __init__(self, sample_frequency_hz, cutoff_frequency_hz, median_window=5):
        if not math.isfinite(sample_frequency_hz) or sample_frequency_hz <= 0:
            raise ValueError("sample_frequency_hz must be a finite number > 0")
        if not math.isfinite(cutoff_frequency_hz) or cutoff_frequency_hz <= 0:
            raise ValueError("cutoff_frequency_hz must be a finite number > 0")
        if not isinstance(median_window, int) or median_window < 1:
            raise ValueError("median_window must be an integer >= 1")

        self._sample_frequency_hz = sample_frequency_hz
        self._cutoff_frequency_hz = cutoff_frequency_hz
        self._median_window = median_window
        period = 1.0 / sample_frequency_hz
        self._alpha = 1.0 - math.exp(
            -2.0 * math.pi * cutoff_frequency_hz * period
        )
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


# EOF - sample_filter.py
