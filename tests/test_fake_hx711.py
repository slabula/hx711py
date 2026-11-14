import pytest

from hx711.core import twos_complement_24bit_to_int
from hx711.fake_hx711 import int_to_twos_complement_24bit


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, 0x000000),
        (1, 0x000001),
        (0x123456, 0x123456),
        (0x7FFFFF, 0x7FFFFF),
        (-1, 0xFFFFFF),
        (-2, 0xFFFFFE),
        (-0x123456, 0xEDCBAA),
        (-0x800000, 0x800000),
        (0x800000, 0x7FFFFF),
        (0xFFFFFF, 0x7FFFFF),
        (-0x800001, 0x800000),
        (-0xFFFFFF, 0x800000),
    ],
)
def test_int_to_twos_complement_24bit(value, expected):
    assert int_to_twos_complement_24bit(value) == expected


@pytest.mark.parametrize(
    "value",
    [-0x800000, -0x123456, -1, 0, 1, 0x123456, 0x7FFFFF],
)
def test_twos_complement_round_trip(value):
    encoded = int_to_twos_complement_24bit(value)

    assert twos_complement_24bit_to_int(encoded) == value
