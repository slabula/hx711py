#! /usr/bin/python3

import argparse
import statistics
import time

from hx711 import HX711


DEFAULT_DOUT_PIN = 5
DEFAULT_PD_SCK_PIN = 6
DEFAULT_RUN_SECONDS = 60.0
DEFAULT_SAMPLES_PER_BATCH = 100
DEFAULT_GLITCH_THRESHOLD = 1.0
DEFAULT_GLITCH_MAD_SCALE = 5.0


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
        "--legacy",
        action="store_true",
        help="use the legacy hx711.v0_5_1 polling method (RPi.GPIO only)",
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
    parser.add_argument(
        "--glitch-threshold",
        type=float,
        default=DEFAULT_GLITCH_THRESHOLD,
        metavar="RAW",
        help="minimum raw deviation from the median to count as a glitch (default: %(default)s)",
    )
    parser.add_argument(
        "--glitch-mad-scale",
        type=float,
        default=DEFAULT_GLITCH_MAD_SCALE,
        metavar="N",
        help="multiply the median absolute deviation to set the glitch threshold (default: %(default)s)",
    )

    args = parser.parse_args(argv)

    if args.legacy and args.gpio != "rpi":
        parser.error("--legacy only supports --gpio rpi")
    if args.seconds <= 0:
        parser.error("--seconds must be greater than 0")
    if args.samples_per_batch < 1:
        parser.error("--samples-per-batch must be at least 1")
    if args.glitch_threshold < 0:
        parser.error("--glitch-threshold must not be negative")
    if args.glitch_mad_scale < 0:
        parser.error("--glitch-mad-scale must not be negative")

    return args


def _import_legacy_module():
    from hx711 import v0_5_1

    return v0_5_1


class LegacyHx711Adapter:
    CH_A_GAIN_128 = 1

    def __init__(self, dout, pd_sck):
        self._module = _import_legacy_module()
        self._hx = self._module.HX711(dout, pd_sck)

    def set_channel_gain(self, enum_value):
        if enum_value != self.CH_A_GAIN_128:
            raise ValueError("legacy driver only supports channel A gain 128")
        self._hx.setGain(128)

    def reset(self):
        self._hx.reset()

    def read_word(self, timeout_seconds=0.5):
        return self._hx.getLong()

    def cleanup(self):
        cleanup = getattr(self._module.GPIO, "cleanup", None)
        if cleanup is not None:
            cleanup()


def build_hx711(args):
    if args.legacy:
        return LegacyHx711Adapter(args.dout, args.pd_sck)

    if args.gpio == "pigpio":
        from hx711.pigpio_hx711 import PigpioHX711

        return PigpioHX711(args.dout, args.pd_sck)

    return HX711(args.dout, args.pd_sck)


def summarize_samples(values, min_glitch_raw, glitch_mad_scale):
    if not values:
        return None

    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    threshold = max(min_glitch_raw, glitch_mad_scale * mad)
    glitch_deviations = [
        deviation for deviation in deviations if deviation > threshold
    ]
    glitch_total = sum(glitch_deviations)

    return {
        "sample_count": len(values),
        "median": median,
        "mad": mad,
        "threshold": threshold,
        "glitch_count": len(glitch_deviations),
        "glitch_total": glitch_total,
        "glitch_mean": (
            glitch_total / len(glitch_deviations) if glitch_deviations else 0.0
        ),
        "glitch_max": max(glitch_deviations) if glitch_deviations else 0.0,
    }


def print_summary(results):
    print()

    if results["batch_count"] == 0:
        print("No samples collected.")
        return

    mean_rate = results["total_rate"] / results["batch_count"]
    print(
        "Overall: Mean {:.2f} Hz, Min {:.2f} Hz, Max {:.2f} Hz, Dropped {}".format(
            mean_rate,
            results["min_rate"],
            results["max_rate"],
            results["drop_count"],
        )
    )

    stats = summarize_samples(
        results["samples"],
        results["min_glitch_raw"],
        results["glitch_mad_scale"],
    )

    if stats is None:
        print("No successful samples collected.")
        return

    glitch_percent = 100.0 * stats["glitch_count"] / stats["sample_count"]
    print(
        "Raw samples: {} collected, median {:g}, MAD {:g}, threshold {:g}".format(
            stats["sample_count"],
            stats["median"],
            stats["mad"],
            stats["threshold"],
        )
    )
    print(
        "Glitches: {} / {} ({:.2f}%), total magnitude {:g}, "
        "mean magnitude {:g}, max magnitude {:g}".format(
            stats["glitch_count"],
            stats["sample_count"],
            glitch_percent,
            stats["glitch_total"],
            stats["glitch_mean"],
            stats["glitch_max"],
        )
    )


def measure_sample_rate(
    hx,
    run_seconds,
    samples_per_batch,
    min_glitch_raw,
    glitch_mad_scale,
):
    results = {
        "batch_count": 0,
        "total_rate": 0.0,
        "min_rate": float("inf"),
        "max_rate": float("-inf"),
        "drop_count": 0,
        "samples": [],
        "min_glitch_raw": min_glitch_raw,
        "glitch_mad_scale": glitch_mad_scale,
    }
    deadline = time.monotonic() + run_seconds

    while time.monotonic() < deadline:
        start_time = time.monotonic()
        batch_samples = []

        for _ in range(samples_per_batch):
            value = hx.read_word()
            if value is None:
                results["drop_count"] += 1
            else:
                batch_samples.append(value)

        results["samples"].extend(batch_samples)

        time_delta = time.monotonic() - start_time
        sample_rate = len(batch_samples) / time_delta if time_delta > 0 else 0.0

        results["batch_count"] += 1
        results["total_rate"] += sample_rate
        results["min_rate"] = min(results["min_rate"], sample_rate)
        results["max_rate"] = max(results["max_rate"], sample_rate)
        mean_rate = results["total_rate"] / results["batch_count"]

        stats = summarize_samples(
            batch_samples, min_glitch_raw, glitch_mad_scale
        )
        if stats is None:
            median_text = "n/a"
            mad_text = "n/a"
            glitch_count = 0
            glitch_max = 0.0
        else:
            median_text = "{:g}".format(stats["median"])
            mad_text = "{:g}".format(stats["mad"])
            glitch_count = stats["glitch_count"]
            glitch_max = stats["glitch_max"]

        print(
            "Sample rate: {:.2f} Hz (Max: {:.2f}, Mean: {:.2f}, Min: {:.2f}) "
            "Dropped: {} Median: {} MAD: {} Glitches: {}/{} Max: {:g}".format(
                sample_rate,
                results["max_rate"],
                mean_rate,
                results["min_rate"],
                results["drop_count"],
                median_text,
                mad_text,
                glitch_count,
                len(batch_samples),
                glitch_max,
            )
        )

    return results


def main(argv=None):
    args = parse_args(argv)
    hx = build_hx711(args)
    results = None

    try:
        hx.set_channel_gain(hx.CH_A_GAIN_128)
        hx.reset()

        results = measure_sample_rate(
            hx,
            args.seconds,
            args.samples_per_batch,
            args.glitch_threshold,
            args.glitch_mad_scale,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        results = None
    finally:
        if results is not None:
            print_summary(results)
        hx.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
