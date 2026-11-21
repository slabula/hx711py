import datetime
import sys

import pytest

import example_client
from example_client import (
    CsvSampleWriter,
    calculate_sample_rate,
    format_reading,
    parse_args,
    parse_serial_line,
    poll_http,
    stream_serial,
)


def test_calculate_sample_rate_uses_timestamps_not_unique_weights():
    samples = [
        {"ts": 10.0, "weight": 1.0},
        {"ts": 10.25, "weight": 1.0},
        {"ts": 10.5, "weight": 2.0},
        {"ts": 10.75, "weight": 3.0},
    ]

    assert calculate_sample_rate(samples) == pytest.approx(4.0)


def test_calculate_sample_rate_counts_repeated_weights():
    samples = [
        {"ts": 10.0 + (index * 0.1), "weight": 5.0}
        for index in range(11)
    ]

    assert calculate_sample_rate(samples) == pytest.approx(10.0)


def test_calculate_sample_rate_requires_multiple_valid_timestamps():
    assert calculate_sample_rate([]) is None
    assert calculate_sample_rate([{"ts": 10.0, "weight": 1.0}]) is None
    assert (
        calculate_sample_rate(
            [
                {"ts": 10.0, "weight": 1.0},
                {"ts": 10.0, "weight": 2.0},
            ]
        )
        is None
    )
    assert (
        calculate_sample_rate(
            [
                {"weight": 1.0},
                {"ts": 10.5, "weight": 1.0},
            ]
        )
        is None
    )


def test_calculate_sample_rate_skips_invalid_timestamps():
    samples = [
        {"ts": 0.0, "weight": 1.0},
        {"ts": float("nan"), "weight": 1.0},
        {"ts": 10.0, "weight": 1.0},
        {"ts": 10.5, "weight": 1.0},
    ]

    assert calculate_sample_rate(samples) == pytest.approx(2.0)


def test_format_reading_includes_sample_rate():
    reading = {
        "ts": 0,
        "weight": 12.345,
        "unit": "kg",
        "samples": [
            {"ts": 10.0, "weight": 1.0},
            {"ts": 10.25, "weight": 1.0},
            {"ts": 10.5, "weight": 2.0},
            {"ts": 10.75, "weight": 3.0},
        ],
    }
    when = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M:%S")

    assert format_reading(reading) == "{}  12.345 kg  rate 4.00 Hz".format(when)


def test_format_reading_without_samples_shows_unavailable_rate():
    reading = {"ts": 0, "weight": 12.345, "unit": "kg"}

    assert format_reading(reading).endswith("rate n/a")


def test_parse_serial_line():
    assert parse_serial_line(b"1794601083.345,12.47\n") == (1794601083.345, 12.47)


def test_parse_serial_line_rejects_bad_lines():
    bad_lines = (
        b"",
        b"1",
        b"1,2,3",
        b"not-a-time,2",
        b"nan,2",
        b"1,inf",
        b"0,2",
        b"-1,2",
    )
    for line in bad_lines:
        try:
            parse_serial_line(line)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for {!r}".format(line))


class FakeSerialPort:
    def __init__(self, lines):
        self.lines = iter(lines)
        self.closed = False

    def readline(self):
        try:
            return next(self.lines)
        except StopIteration:
            raise KeyboardInterrupt

    def close(self):
        self.closed = True


class FakeSerialModule:
    def __init__(self, port):
        self.port = port
        self.open_args = None

    def Serial(self, path, baudrate, timeout):
        self.open_args = (path, baudrate, timeout)
        return self.port


def test_stream_serial_prints_samples_and_estimates_rate(monkeypatch, capsys):
    port = FakeSerialPort([b"10.0,1.0\n", b"10.25,2.0\n"])
    module = FakeSerialModule(port)
    monkeypatch.setattr(example_client, "import_serial_module", lambda: module)

    try:
        stream_serial("/dev/ttyACM0", 115200, 1.0, "kg")
    except KeyboardInterrupt:
        pass

    assert module.open_args == ("/dev/ttyACM0", 115200, 1.0)
    assert port.closed is True

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Reading from /dev/ttyACM0"
    assert lines[1].endswith("1.000 kg  rate n/a")
    assert lines[2].endswith("2.000 kg  rate 4.00 Hz")


def test_stream_serial_waits_for_a_complete_line(monkeypatch, capsys):
    port = FakeSerialPort([b"10.0,1.", b"0\n"])
    module = FakeSerialModule(port)
    monkeypatch.setattr(example_client, "import_serial_module", lambda: module)

    try:
        stream_serial("/dev/ttyACM0", 115200, 1.0, None)
    except KeyboardInterrupt:
        pass

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[1].endswith("1.000  rate n/a")


def test_csv_option_is_parsed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["example_client.py", "--csv", "samples.csv"])

    assert parse_args().csv == "samples.csv"


def test_csv_writer_writes_header_and_valid_samples(tmp_path):
    path = tmp_path / "samples.csv"
    writer = CsvSampleWriter(str(path))

    assert writer.write({"ts": 10.0, "weight": 1.5}) is True
    assert writer.write({"ts": 10.25, "weight": float("nan")}) is False
    assert writer.write({"ts": 10.5, "weight": 2.5}, deduplicate=True) is True
    assert writer.write({"ts": 10.5, "weight": 2.5}, deduplicate=True) is False

    writer.close()

    assert path.read_text().splitlines() == [
        "timestamp,weight",
        "10.0,1.5",
        "10.5,2.5",
    ]


def test_csv_writer_appends_without_repeating_header(tmp_path):
    path = tmp_path / "samples.csv"
    path.write_text("timestamp,weight\n10.0,1.0\n")

    writer = CsvSampleWriter(str(path))
    writer.write({"ts": 10.25, "weight": 2.0})
    writer.close()

    assert path.read_text().splitlines() == [
        "timestamp,weight",
        "10.0,1.0",
        "10.25,2.0",
    ]


def test_poll_http_writes_each_history_sample_once(monkeypatch, tmp_path):
    payload = {
        "ts": 10.25,
        "weight": 2.0,
        "samples": [
            {"ts": 10.0, "weight": 1.0},
            {"ts": 10.25, "weight": 2.0},
        ],
    }
    polls = [payload, payload]

    def fake_fetch(url, timeout):
        if not polls:
            raise KeyboardInterrupt
        return polls.pop(0)

    monkeypatch.setattr(example_client, "fetch", fake_fetch)
    monkeypatch.setattr(example_client.time, "sleep", lambda seconds: None)

    path = tmp_path / "http.csv"
    writer = CsvSampleWriter(str(path))
    try:
        poll_http("http://example.test/weight", 0.1, 1.0, writer)
    except KeyboardInterrupt:
        pass
    finally:
        writer.close()

    assert path.read_text().splitlines() == [
        "timestamp,weight",
        "10.0,1.0",
        "10.25,2.0",
    ]


def test_poll_http_writes_latest_reading_without_samples(monkeypatch, tmp_path):
    polls = [{"ts": 10.0, "weight": 1.0}]

    def fake_fetch(url, timeout):
        if not polls:
            raise KeyboardInterrupt
        return polls.pop(0)

    monkeypatch.setattr(example_client, "fetch", fake_fetch)
    monkeypatch.setattr(example_client.time, "sleep", lambda seconds: None)

    path = tmp_path / "http.csv"
    writer = CsvSampleWriter(str(path))
    try:
        poll_http("http://example.test/weight", 0.1, 1.0, writer)
    except KeyboardInterrupt:
        pass
    finally:
        writer.close()

    assert path.read_text().splitlines() == ["timestamp,weight", "10.0,1.0"]


def test_stream_serial_writes_every_sample_to_csv(monkeypatch, tmp_path):
    port = FakeSerialPort(
        [b"10.0,1.0\n", b"10.25,2.0\n", b"10.25,2.0\n"]
    )
    module = FakeSerialModule(port)
    monkeypatch.setattr(example_client, "import_serial_module", lambda: module)

    path = tmp_path / "serial.csv"
    writer = CsvSampleWriter(str(path))
    try:
        stream_serial("/dev/ttyACM0", 115200, 1.0, "kg", writer)
    except KeyboardInterrupt:
        pass
    finally:
        writer.close()

    assert path.read_text().splitlines() == [
        "timestamp,weight",
        "10.0,1.0",
        "10.25,2.0",
        "10.25,2.0",
    ]
