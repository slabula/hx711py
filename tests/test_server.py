import threading

import pytest

from hx711_server import LatestReading, build_sample_filter, parse_args


def test_latest_reading_starts_empty():
    assert LatestReading().get() is None


def test_latest_reading_returns_most_recent_value():
    reading = LatestReading()

    reading.set({"ts": 1.0, "weight": 2.0, "unit": "kg"})
    reading.set({"ts": 3.0, "weight": 4.0, "unit": "kg"})

    assert reading.get() == {"ts": 3.0, "weight": 4.0, "unit": "kg"}


def test_latest_reading_can_be_reset_to_none():
    reading = LatestReading()
    reading.set({"weight": 2.0})
    reading.set(None)

    assert reading.get() is None


def test_latest_reading_is_thread_safe():
    reading = LatestReading()
    errors = []

    def writer():
        try:
            for seq in range(1000):
                reading.set({"seq": seq})
        except Exception as exc:
            errors.append(exc)

    def reader():
        try:
            for _ in range(1000):
                value = reading.get()
                if value is not None and "seq" not in value:
                    raise AssertionError(value)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_filter_is_disabled_by_default():
    args = parse_args([])

    assert args.filter_sample_rate == 10.0
    assert args.filter_median_window == 5
    assert build_sample_filter(args) is None


def test_filter_settings_are_parsed():
    args = parse_args(
        [
            "--filter-cutoff",
            "5.5",
            "--filter-sample-rate",
            "80",
            "--filter-median-window",
            "3",
        ]
    )

    sample_filter = build_sample_filter(args)

    assert sample_filter._sample_frequency_hz == 80.0
    assert sample_filter._cutoff_frequency_hz == 5.5
    assert sample_filter._median_window == 3


@pytest.mark.parametrize(
    "argv, match",
    [
        (["--filter-cutoff", "0"], "cutoff_frequency_hz"),
        (["--filter-cutoff", "5", "--filter-sample-rate", "0"], "sample_frequency_hz"),
        (["--filter-cutoff", "5", "--filter-median-window", "0"], "median_window"),
    ],
)
def test_invalid_filter_settings_raise_value_error(argv, match):
    args = parse_args(argv)

    with pytest.raises(ValueError, match=match):
        build_sample_filter(args)
