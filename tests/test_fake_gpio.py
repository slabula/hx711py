import time

import pytest

import hx711.core as core
from hx711.core import HX711
from hx711.fake_gpio import FakeGpio
from hx711.fake_hx711 import FakeHx711


def test_fake_gpio_default_device_is_used_for_all_pins():
    fake = FakeHx711()
    fake.inject_raw_samples([0x001234])
    gpio = FakeGpio(fake)

    hx = HX711(5, 6, gpio_module=gpio)
    hx.reset()
    time.sleep(0.02)

    assert hx.read_word() == 0x001234


def test_fake_gpio_supports_multiple_devices_on_one_instance():
    device_a = FakeHx711()
    device_b = FakeHx711()
    device_a.inject_raw_samples([0x001234])
    device_b.inject_raw_samples([0x005678])

    gpio = FakeGpio()
    gpio.add_device(5, 6, device_a)
    gpio.add_device(7, 8, device_b)

    hx_a = HX711(5, 6, gpio_module=gpio)
    hx_b = HX711(7, 8, gpio_module=gpio)

    hx_a.reset()
    hx_b.reset()
    time.sleep(0.02)

    assert hx_a.read_word() == 0x001234
    assert hx_b.read_word() == 0x005678


def test_fake_gpio_rejects_unconfigured_pins():
    gpio = FakeGpio(FakeHx711())

    with pytest.raises(ValueError):
        gpio.input(5)

    with pytest.raises(ValueError):
        gpio.output(6, True)


def test_fallback_hx711_instances_get_independent_fake_devices(monkeypatch):
    monkeypatch.setattr(core, "GPIO", None)

    hx_a = HX711(5, 6)
    hx_b = HX711(7, 8)

    assert hx_a._gpio is not hx_b._gpio
    assert hx_a._gpio._pin_devices[5] is not hx_b._gpio._pin_devices[7]
