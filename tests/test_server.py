import threading

import pytest

from hx711 import HX711
from hx711_server import (
    LatestReading,
    READER_JOIN_TIMEOUT_SECONDS,
    build_hx711,
    build_sample_filter,
    parse_args,
    read_forever,
    stop_reader_and_cleanup,
)


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

    assert args.filter_sample_rate == 80.0
    assert args.filter_median_window == 5
    assert args.gpio == "rpi"
    assert build_sample_filter(args) is None


def test_gpio_backend_is_parsed():
    args = parse_args(["--gpio", "pigpio"])

    assert args.gpio == "pigpio"


def test_build_hx711_uses_rpi_backend_by_default():
    hx = build_hx711(parse_args(["--dout", "5", "--pd-sck", "6"]))

    assert isinstance(hx, HX711)
    assert hx._dout == 5
    assert hx._pd_sck == 6
    hx.cleanup()


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


class StopAfterOneRead:
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.reads = 0

    def read_weight(self, timeout_seconds=0.5):
        self.reads += 1
        if self.reads > 1:
            raise AssertionError("read_forever ignored stop event")
        self.stop_event.set()
        return 12.5


class FakeReaderThread:
    def __init__(self, alive_after_join):
        self.alive = True
        self.alive_after_join = alive_after_join
        self.join_timeout = None

    def join(self, timeout=None):
        self.join_timeout = timeout
        self.alive = self.alive_after_join

    def is_alive(self):
        return self.alive


class CleanupRecorder:
    def __init__(self):
        self.cleaned = False

    def cleanup(self):
        self.cleaned = True


def test_read_forever_stops_after_stop_event_is_set():
    stop_event = threading.Event()
    hx = StopAfterOneRead(stop_event)
    reading = LatestReading()

    read_forever(hx, reading, "kg", stop_event)

    assert hx.reads == 1
    assert reading.get()["weight"] == 12.5
    assert reading.get()["unit"] == "kg"


def test_read_forever_does_not_read_when_already_stopped():
    stop_event = threading.Event()
    stop_event.set()
    hx = StopAfterOneRead(stop_event)
    reading = LatestReading()

    read_forever(hx, reading, "kg", stop_event)

    assert hx.reads == 0
    assert reading.get() is None


def test_stop_reader_and_cleanup_joins_before_cleanup():
    stop_event = threading.Event()
    read_thread = FakeReaderThread(alive_after_join=False)
    hx = CleanupRecorder()

    stopped = stop_reader_and_cleanup(read_thread, stop_event, hx)

    assert stopped is True
    assert stop_event.is_set()
    assert read_thread.join_timeout == READER_JOIN_TIMEOUT_SECONDS
    assert hx.cleaned is True


def test_stop_reader_and_cleanup_skips_cleanup_if_reader_is_alive():
    stop_event = threading.Event()
    read_thread = FakeReaderThread(alive_after_join=True)
    hx = CleanupRecorder()

    stopped = stop_reader_and_cleanup(read_thread, stop_event, hx)

    assert stopped is False
    assert stop_event.is_set()
    assert hx.cleaned is False
