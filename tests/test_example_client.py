import datetime

from example_client import calculate_sample_rate, format_reading


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
