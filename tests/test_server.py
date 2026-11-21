import threading

import pytest

from hx711 import HX711
from hx711_server import (
    DEFAULT_SERIAL_BAUDRATE,
    HISTORY_SIZE,
    READER_JOIN_TIMEOUT_SECONDS,
    CsvSerialPublisher,
    ReadingHistory,
    build_hx711,
    build_sample_filter,
    parse_args,
    read_forever,
    stop_reader_and_cleanup,
)


def test_reading_history_starts_empty():
    assert ReadingHistory().get() is None


def test_reading_history_returns_latest_value_and_all_samples():
    reading = ReadingHistory()

    reading.set({"ts": 1.0, "weight": 2.0, "unit": "kg"})
    reading.set({"ts": 3.0, "weight": 4.0, "unit": "kg"})

    assert reading.get() == {
        "ts": 3.0,
        "weight": 4.0,
        "unit": "kg",
        "samples": [
            {"ts": 1.0, "weight": 2.0, "unit": "kg"},
            {"ts": 3.0, "weight": 4.0, "unit": "kg"},
        ],
    }


def test_reading_history_keeps_only_the_most_recent_samples():
    reading = ReadingHistory()

    for seq in range(HISTORY_SIZE + 10):
        reading.set({"seq": seq})

    payload = reading.get()

    assert len(payload["samples"]) == HISTORY_SIZE
    assert payload["seq"] == HISTORY_SIZE + 9
    assert payload["samples"][0]["seq"] == 10
    assert payload["samples"][-1]["seq"] == HISTORY_SIZE + 9


def test_reading_history_can_be_reset_to_none():
    reading = ReadingHistory()
    reading.set({"weight": 2.0})
    reading.set(None)

    assert reading.get() is None


def test_reading_history_is_thread_safe():
    reading = ReadingHistory()
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
                if value is not None and (
                    "seq" not in value or "samples" not in value
                ):
                    raise AssertionError(value)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
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
    reading = ReadingHistory()

    read_forever(hx, reading, "kg", stop_event)

    assert hx.reads == 1
    assert reading.get()["weight"] == 12.5
    assert reading.get()["unit"] == "kg"


def test_read_forever_does_not_read_when_already_stopped():
    stop_event = threading.Event()
    stop_event.set()
    hx = StopAfterOneRead(stop_event)
    reading = ReadingHistory()

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


class RecordingPort:
    def __init__(self, write_error=None):
        self.writes = []
        self.closed = False
        self.write_error = write_error

    def write(self, data):
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(data)

    def close(self):
        self.closed = True


def test_csv_serial_publisher_writes_timestamp_and_weight():
    port = RecordingPort()
    publisher = CsvSerialPublisher(port)

    publisher.publish(1.25, 12.5)
    publisher.close()

    assert port.writes == [b"1.25,12.5\n"]
    assert port.closed is True


def test_csv_serial_publisher_drops_failed_writes(capsys):
    port = RecordingPort(write_error=OSError("device gone"))
    publisher = CsvSerialPublisher(port)

    publisher.publish(1.0, 2.0)
    publisher.publish(3.0, 4.0)

    assert port.writes == []
    assert "dropping samples" in capsys.readouterr().err


def test_parse_args_serial_defaults():
    args = parse_args([])

    assert args.serial is None
    assert args.serial_baudrate == DEFAULT_SERIAL_BAUDRATE

    args = parse_args(["--serial", "/dev/ttyGS0", "--serial-baudrate", "9600"])

    assert args.serial == "/dev/ttyGS0"
    assert args.serial_baudrate == 9600


class StopAfterTwoReads:
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.values = iter([1.0, 2.0])

    def read_weight(self, timeout_seconds=0.5):
        try:
            return next(self.values)
        except StopIteration:
            self.stop_event.set()
            return None


def test_read_forever_publishes_each_sample():
    stop_event = threading.Event()
    hx = StopAfterTwoReads(stop_event)
    reading = ReadingHistory()
    port = RecordingPort()
    publisher = CsvSerialPublisher(port)

    read_forever(hx, reading, "kg", stop_event, publisher)

    assert len(port.writes) == 2
    assert port.writes[0].endswith(b",1.0\n")
    assert port.writes[1].endswith(b",2.0\n")
    assert [sample["weight"] for sample in reading.get()["samples"]] == [1.0, 2.0]


def test_stop_reader_and_cleanup_closes_publisher():
    stop_event = threading.Event()
    read_thread = FakeReaderThread(alive_after_join=False)
    hx = CleanupRecorder()
    port = RecordingPort()
    publisher = CsvSerialPublisher(port)

    stopped = stop_reader_and_cleanup(read_thread, stop_event, hx, publisher)

    assert stopped is True
    assert port.closed is True
