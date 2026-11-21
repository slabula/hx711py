#! /usr/bin/python3

"""
Read an hx711_server.py instance and print timestamp/weight/sample-rate values.

By default this polls the HTTP /weight endpoint. With --serial it instead reads
"timestamp,weight" lines from a USB ACM device such as /dev/ttyACM0.
"""

import argparse
import collections
import datetime
import json
import math
import time
import urllib.error
import urllib.request


DEFAULT_URL = "http://raspberrypi.local:8080/weight"
DEFAULT_INTERVAL = 0.5
DEFAULT_TIMEOUT = 2.0
DEFAULT_SERIAL_BAUDRATE = 115200
DEFAULT_SERIAL_RETRY_SECONDS = 1.0
SERIAL_HISTORY_SIZE = 100
MAX_SERIAL_LINE_BYTES = 1024


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read HX711 samples over HTTP or a USB serial device."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="reading URL (default: %(default)s)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="seconds between polls (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="request/serial timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--serial",
        metavar="DEVICE",
        help="read 'timestamp,weight' lines from DEVICE instead of HTTP",
    )
    parser.add_argument(
        "--serial-baudrate",
        type=int,
        default=DEFAULT_SERIAL_BAUDRATE,
        metavar="BAUD",
        help="serial baud rate (default: %(default)s; ignored by USB ACM)",
    )
    parser.add_argument(
        "--unit",
        help="unit label to print for serial samples (not sent on the wire)",
    )
    return parser.parse_args()


def fetch(url, timeout):
    response = urllib.request.urlopen(url, timeout=timeout)
    try:
        return json.loads(response.read().decode("utf-8"))
    finally:
        response.close()


def import_serial_module():
    try:
        import serial
    except ImportError:
        raise SystemExit("error: --serial requires pyserial (pip install pyserial)")
    return serial


def parse_serial_line(line):
    """Parse one complete 'timestamp,weight' line from the serial stream.

    Malformed lines, non-finite values, and non-positive timestamps raise
    ValueError so the caller can skip them.
    """
    parts = line.decode("utf-8", errors="replace").strip().split(",")
    if len(parts) != 2:
        raise ValueError("expected 'timestamp,weight'")

    try:
        ts = float(parts[0])
        weight = float(parts[1])
    except ValueError:
        raise ValueError("timestamp and weight must be floats")

    if not math.isfinite(ts) or not math.isfinite(weight):
        raise ValueError("timestamp and weight must be finite")
    if ts <= 0:
        raise ValueError("timestamp must be positive")

    return ts, weight


def calculate_sample_rate(samples):
    if not samples:
        return None

    unique_samples = []
    seen_values = set()
    for sample in samples:
        value = sample.get("weight")
        if value in seen_values:
            continue
        seen_values.add(value)
        unique_samples.append(sample)

    if len(unique_samples) < 2:
        return None

    first = unique_samples[0].get("ts")
    last = unique_samples[-1].get("ts")
    if first is None or last is None or last <= first:
        return None

    return len(unique_samples) / (last - first)


def format_reading(reading):
    when = datetime.datetime.fromtimestamp(reading["ts"])
    text = "{}  {:.3f}".format(
        when.strftime("%Y-%m-%d %H:%M:%S"),
        reading["weight"],
    )

    unit = reading.get("unit")
    if unit:
        text += " {}".format(unit)

    sample_rate = calculate_sample_rate(reading.get("samples"))
    if sample_rate is None:
        text += "  rate n/a"
    else:
        text += "  rate {:.2f} Hz".format(sample_rate)

    return text


def poll_http(url, interval, timeout):
    while True:
        try:
            reading = fetch(url, timeout)
            print(format_reading(reading))
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                print("Waiting for the first reading...")
            else:
                print("HTTP error: {}".format(exc))
        except Exception as exc:
            print("Error: {}".format(exc))

        time.sleep(interval)


def stream_serial(path, baudrate, timeout, unit):
    serial = import_serial_module()
    history = collections.deque(maxlen=SERIAL_HISTORY_SIZE)
    port = None

    print("Reading from {}".format(path))
    pending = b""
    while True:
        try:
            if port is None:
                port = serial.Serial(path, baudrate, timeout=timeout)

            chunk = port.readline()
            if not chunk:
                continue

            pending += chunk
            if len(pending) > MAX_SERIAL_LINE_BYTES:
                # No newline in a long time: treat it as garbage, not a sample.
                pending = b""
                continue
            if not pending.endswith(b"\n"):
                # pyserial returns a partial line when the read timeout expires.
                continue

            line, pending = pending, b""
            try:
                ts, weight = parse_serial_line(line)
            except ValueError:
                continue

            sample = {"ts": ts, "weight": weight}
            if unit:
                sample["unit"] = unit
            history.append(sample)

            reading = dict(sample)
            reading["samples"] = list(history)
            print(format_reading(reading))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print("Serial error: {}".format(exc))
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
                port = None
            time.sleep(DEFAULT_SERIAL_RETRY_SECONDS)


def main():
    args = parse_args()

    try:
        if args.serial:
            stream_serial(args.serial, args.serial_baudrate, args.timeout, args.unit)
        else:
            poll_http(args.url, args.interval, args.timeout)
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()


# EOF - example_client.py
