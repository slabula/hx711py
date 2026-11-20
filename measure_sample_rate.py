#! /usr/bin/python3

import argparse
import time

from hx711 import HX711


DEFAULT_DOUT_PIN = 5
DEFAULT_PD_SCK_PIN = 6
DEFAULT_RUN_SECONDS = 60.0
DEFAULT_SAMPLES_PER_BATCH = 100


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the sample rate achieved by an HX711 reader."
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
        "--seconds",
        type=float,
        default=DEFAULT_RUN_SECONDS,
        metavar="SECONDS",
        help="how long to measure (default: %(default)s)",
    )
    parser.add_argument(
        "--samples-per-batch",
        type=int,
        default=DEFAULT_SAMPLES_PER_BATCH,
        metavar="N",
        help="samples per timing batch (default: %(default)s)",
    )

    args = parser.parse_args(argv)

    if args.seconds <= 0:
        parser.error("--seconds must be greater than 0")
    if args.samples_per_batch < 1:
        parser.error("--samples-per-batch must be at least 1")

    return args


def build_hx711(args):
    if args.gpio == "pigpio":
        from hx711.pigpio_hx711 import PigpioHX711

        return PigpioHX711(args.dout, args.pd_sck)

    return HX711(args.dout, args.pd_sck)


def print_summary(batch_count, total_rate, min_rate, max_rate, drop_count):
    print()

    if batch_count == 0:
        print("No samples collected.")
        return

    mean_rate = total_rate / batch_count
    print(
        "Overall: Mean {:.2f} Hz, Min {:.2f} Hz, Max {:.2f} Hz, Dropped {}".format(
            mean_rate, min_rate, max_rate, drop_count
        )
    )


def measure_sample_rate(hx, run_seconds, samples_per_batch):
    deadline = time.monotonic() + run_seconds
    batch_count = 0
    total_rate = 0.0
    min_rate = float("inf")
    max_rate = float("-inf")
    drop_count = 0

    while time.monotonic() < deadline:
        start_time = time.monotonic()
        samples_read = 0

        for _ in range(samples_per_batch):
            if hx.read_word() is not None:
                samples_read += 1
            else:
                drop_count += 1

        time_delta = time.monotonic() - start_time
        sample_rate = samples_read / time_delta if time_delta > 0 else 0.0

        batch_count += 1
        total_rate += sample_rate
        min_rate = min(min_rate, sample_rate)
        max_rate = max(max_rate, sample_rate)
        mean_rate = total_rate / batch_count

        print(
            "Sample rate: {:.2f} Hz (Max: {:.2f}, Mean: {:.2f}, Min: {:.2f}) "
            "Dropped: {}".format(
                sample_rate, max_rate, mean_rate, min_rate, drop_count
            )
        )

    return batch_count, total_rate, min_rate, max_rate, drop_count


def main(argv=None):
    args = parse_args(argv)
    hx = build_hx711(args)
    results = None

    try:
        hx.set_channel_gain(hx.CH_A_GAIN_128)
        hx.reset()

        results = measure_sample_rate(
            hx, args.seconds, args.samples_per_batch
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        results = None
    finally:
        if results is not None:
            print_summary(*results)
        hx.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
