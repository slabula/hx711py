import datetime

import example_client
from example_client import (
    calculate_sample_rate,
    format_reading,
    parse_serial_line,
    stream_serial,
)


def test_calculate_sample_rate_counts_unique_values():
    samples = [
        {"ts": 10.0, "weight": 1.0},
        {"ts": 10.25, "weight": 1.0},
        {"ts": 10.5, "weight": 2.0},
        {"ts": 10.75, "weight": 3.0},
    ]

    assert calculate_sample_rate(samples) == 4.0


def test_calculate_sample_rate_requires_multiple_unique_samples():
    assert calculate_sample_rate([]) is None
    assert calculate_sample_rate([{"ts": 10.0, "weight": 1.0}]) is None
    assert (
        calculate_sample_rate(
            [
                {"ts": 10.0, "weight": 1.0},
                {"ts": 10.5, "weight": 1.0},
            ]
        )
        is None
    )
    assert (
        calculate_sample_rate(
            [
                {"ts": 10.0, "weight": 1.0},
                {"ts": 10.0, "weight": 2.0},
            ]
        )
        is None
    )


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
    assert lines[2].endswith("2.000 kg  rate 8.00 Hz")


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
