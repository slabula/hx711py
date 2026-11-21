#! /usr/bin/python3

"""
Serve the latest 100 HX711 readings over HTTP as JSON, and optionally stream
one "timestamp,weight" line per sample to a serial device such as /dev/ttyGS0
on a Pi Zero W configured as a USB ACM gadget.

Run this on the machine connected to the HX711; clients poll /weight.
"""

import argparse
import collections
import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from hx711 import (
    ExponentialFilter,
    HampelExponentialFilter,
    HampelFilter,
    HX711,
    MedianExponentialFilter,
    MedianFilter,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_DOUT_PIN = 5
DEFAULT_PD_SCK_PIN = 6
DEFAULT_FILTER_SAMPLE_RATE_HZ = 80.0
DEFAULT_FILTER_WINDOW = 5
DEFAULT_FILTER_MEDIAN_WINDOW = DEFAULT_FILTER_WINDOW
DEFAULT_HAMPEL_MAD_THRESHOLD = 3.0
DEFAULT_HAMPEL_MAD_SCALE = 1.4826
DEFAULT_HAMPEL_MIN_MAD = 0.0
FILTER_CHOICES = (
    "none",
    "median",
    "ema",
    "median-ema",
    "hampel",
    "hampel-ema",
)
HISTORY_SIZE = 100
READ_TIMEOUT_SECONDS = 0.5
READER_JOIN_TIMEOUT_SECONDS = 1.0
DEFAULT_SERIAL_BAUDRATE = 115200

GAIN_ENUMS = {
    128: HX711.CH_A_GAIN_128,
    64: HX711.CH_A_GAIN_64,
    32: HX711.CH_B_GAIN_32,
}


class ReadingHistory:
    """Thread-safe holder for the most recent readings."""

    def __init__(self, capacity=HISTORY_SIZE):
        self._lock = threading.Lock()
        self._capacity = capacity
        self._samples = collections.deque(maxlen=capacity)

    def set(self, value):
        if value is None:
            self.clear()
            return

        with self._lock:
            self._samples.append(dict(value))

    def clear(self):
        with self._lock:
            self._samples.clear()

    def get(self):
        with self._lock:
            if not self._samples:
                return None

            samples = list(self._samples)
            payload = dict(samples[-1])
            payload["samples"] = samples
            return payload


LatestReading = ReadingHistory


class CsvSerialPublisher:
    """Streams one "timestamp,weight" line per sample to a serial port.

    The port only needs a write(bytes) method and a close() method, which makes
    the publisher easy to test without real hardware. Write errors drop the
    current sample rather than stalling the reader thread; USB ACM has no flow
    control here, so a slow host should not back up the HX711 reader.
    """

    def __init__(self, port):
        self._port = port
        self._reported_error = False

    def publish(self, ts, weight):
        line = "{},{}\n".format(ts, weight)
        try:
            self._port.write(line.encode("utf-8"))
        except Exception as exc:
            if not self._reported_error:
                print(
                    "serial write failed (dropping samples): {}".format(exc),
                    file=sys.stderr,
                )
                self._reported_error = True

    def close(self):
        self._port.close()


def open_serial_publisher(path, baudrate=DEFAULT_SERIAL_BAUDRATE):
    """Open a serial device lazily so HTTP-only users do not need pyserial."""
    try:
        import serial
    except ImportError:
        raise SystemExit("error: --serial requires pyserial (pip install pyserial)")

    try:
        port = serial.Serial(path, baudrate, write_timeout=0, timeout=0)
    except Exception as exc:
        raise SystemExit("error: cannot open serial device {}: {}".format(path, exc))

    return CsvSerialPublisher(port)


def read_forever(hx, reading, unit, stop_event, publisher=None):
    while not stop_event.is_set():
        weight = hx.read_weight(timeout_seconds=READ_TIMEOUT_SECONDS)
        if weight is not None:
            ts = time.time()
            reading.set({"ts": ts, "weight": weight, "unit": unit})
            if publisher is not None:
                publisher.publish(ts, weight)


def stop_reader_and_cleanup(read_thread, stop_event, hx, publisher=None):
    stop_event.set()
    read_thread.join(timeout=READER_JOIN_TIMEOUT_SECONDS)
    if read_thread.is_alive():
        return False

    hx.cleanup()
    if publisher is not None:
        publisher.close()
    return True


class Handler(BaseHTTPRequestHandler):
    reading = None  # set in main()

    def do_GET(self):
        if self.path not in ("/", "/weight"):
            self.send_error(404)
            return

        payload = self.reading.get()
        if payload is None:
            self.send_error(503, "No reading yet")
            return

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _handle_sigterm(signum, frame):
    raise KeyboardInterrupt


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Serve the latest HX711 reading over HTTP as JSON."
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="bind address (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP port (default: %(default)s)",
    )
    parser.add_argument(
        "--dout",
        type=int,
        default=DEFAULT_DOUT_PIN,
        help="DOUT GPIO pin (default: %(default)s)",
    )
    parser.add_argument(
        "--pd-sck",
        type=int,
        default=DEFAULT_PD_SCK_PIN,
        help="PD_SCK GPIO pin (default: %(default)s)",
    )
    parser.add_argument(
        "--gpio",
        choices=("rpi", "pigpio"),
        default="rpi",
        help="GPIO backend (default: %(default)s)",
    )
    parser.add_argument(
        "--gain",
        type=int,
        choices=(128, 64, 32),
        default=128,
        help="channel A gain 128/64, or channel B gain 32 (default: %(default)s)",
    )
    parser.add_argument(
        "--m",
        type=float,
        help="calibration m (default: 1.0)",
    )
    parser.add_argument(
        "--c",
        type=float,
        help="calibration c (default: 0.0)",
    )
    parser.add_argument(
        "--unit",
        default="units",
        help="unit label reported to clients (default: %(default)s)",
    )
    parser.add_argument(
        "--serial",
        metavar="DEVICE",
        help="also stream 'timestamp,weight' lines to DEVICE, e.g. /dev/ttyGS0",
    )
    parser.add_argument(
        "--serial-baudrate",
        type=int,
        default=DEFAULT_SERIAL_BAUDRATE,
        metavar="BAUD",
        help="serial baud rate (default: %(default)s; ignored by USB ACM)",
    )
    parser.add_argument(
        "--filter",
        choices=FILTER_CHOICES,
        default=None,
        help=(
            "filter type: none, median, ema, median-ema, hampel, or hampel-ema "
            "(default: median-ema when --filter-cutoff is set, otherwise none)"
        ),
    )
    parser.add_argument(
        "--filter-cutoff",
        type=float,
        metavar="HZ",
        help=(
            "low-pass cutoff in Hz for ema, median-ema, and hampel-ema; "
            "supplying it without --filter selects median-ema for compatibility"
        ),
    )
    parser.add_argument(
        "--filter-sample-rate",
        type=float,
        default=DEFAULT_FILTER_SAMPLE_RATE_HZ,
        metavar="HZ",
        help="sample rate for filtering in Hz (default: %(default)s)",
    )
    parser.add_argument(
        "--filter-window",
        "--filter-median-window",
        dest="filter_window",
        type=int,
        default=DEFAULT_FILTER_WINDOW,
        metavar="N",
        help="window size for median, median-ema, hampel, and hampel-ema (default: %(default)s)",
    )
    parser.add_argument(
        "--filter-mad-threshold",
        type=float,
        default=DEFAULT_HAMPEL_MAD_THRESHOLD,
        metavar="N",
        help="Hampel MAD threshold (default: %(default)s)",
    )
    parser.add_argument(
        "--filter-mad-scale",
        type=float,
        default=DEFAULT_HAMPEL_MAD_SCALE,
        metavar="N",
        help="Hampel MAD scale factor (default: %(default)s)",
    )
    parser.add_argument(
        "--filter-min-mad",
        type=float,
        default=DEFAULT_HAMPEL_MIN_MAD,
        metavar="N",
        help="absolute minimum Hampel rejection limit (default: %(default)s)",
    )

    args = parser.parse_args(argv)

    # Backwards compatibility with code that reads this attribute directly.
    args.filter_median_window = args.filter_window

    if args.filter is None:
        if args.filter_cutoff is not None:
            args.filter = "median-ema"
        else:
            args.filter = "none"

    return args


def _filter_cutoff(args, filter_name):
    if args.filter_cutoff is None:
        raise ValueError("--filter {} requires --filter-cutoff".format(filter_name))
    return args.filter_cutoff


def build_sample_filter(args):
    filter_name = getattr(args, "filter", None)
    if filter_name is None:
        filter_name = "median-ema" if args.filter_cutoff is not None else "none"

    if filter_name == "none":
        return None

    window = getattr(
        args, "filter_window", getattr(args, "filter_median_window", DEFAULT_FILTER_WINDOW)
    )

    if filter_name == "median":
        return MedianFilter(window=window)

    if filter_name == "ema":
        return ExponentialFilter(
            sample_frequency_hz=args.filter_sample_rate,
            cutoff_frequency_hz=_filter_cutoff(args, filter_name),
        )

    if filter_name == "median-ema":
        return MedianExponentialFilter(
            sample_frequency_hz=args.filter_sample_rate,
            cutoff_frequency_hz=_filter_cutoff(args, filter_name),
            median_window=window,
        )

    hampel_kwargs = {
        "window": window,
        "threshold": args.filter_mad_threshold,
        "min_mad": args.filter_min_mad,
        "mad_scale": args.filter_mad_scale,
    }

    if filter_name == "hampel":
        return HampelFilter(**hampel_kwargs)

    if filter_name == "hampel-ema":
        return HampelExponentialFilter(
            sample_frequency_hz=args.filter_sample_rate,
            cutoff_frequency_hz=_filter_cutoff(args, filter_name),
            **hampel_kwargs
        )

    raise ValueError("unknown filter type: {!r}".format(filter_name))


def build_hx711(args):
    if args.gpio == "pigpio":
        from hx711.pigpio_hx711 import PigpioHX711

        return PigpioHX711(args.dout, args.pd_sck)

    return HX711(args.dout, args.pd_sck)


def main():
    args = parse_args()

    try:
        sample_filter = build_sample_filter(args)
    except ValueError as exc:
        raise SystemExit("error: {}".format(exc))

    hx = build_hx711(args)

    if args.m is not None:
        hx.set_m(args.m)
    if args.c is not None:
        hx.set_c(args.c)

    hx.reset()
    hx.set_channel_gain(GAIN_ENUMS[args.gain])

    if sample_filter is not None:
        hx.set_filter(sample_filter)

    reading = ReadingHistory()
    Handler.reading = reading

    publisher = None
    if args.serial:
        publisher = open_serial_publisher(args.serial, args.serial_baudrate)
        print("Streaming samples to {}".format(args.serial))

    stop_event = threading.Event()
    read_thread = threading.Thread(
        target=read_forever,
        args=(hx, reading, args.unit, stop_event, publisher),
        daemon=True,
    )
    read_thread.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Serving http://{}:{}/weight".format(args.host, args.port))
    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop_reader_and_cleanup(read_thread, stop_event, hx, publisher)


if __name__ == "__main__":
    main()


# EOF - hx711_server.py
