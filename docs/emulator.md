# Emulator

When `RPi.GPIO` is unavailable, each `HX711` instance automatically gets its own
`FakeGpio` and `FakeHx711`, so imports and examples still work without hardware.
`example_emulator.py` shows how to inject your own samples:

```bash
python example_emulator.py
```

For explicit control:

```python
from hx711 import HX711
from hx711.fake_gpio import FakeGpio
from hx711.fake_hx711 import FakeHx711

fake_hx711 = FakeHx711()
fake_hx711.inject_raw_samples([0, 1000, 2000])

hx = HX711(5, 6, gpio_module=FakeGpio(fake_hx711))
hx.reset()

print(hx.read_word())
```

`FakeGpio` tracks pins independently. To run several emulated readers on one
`FakeGpio` instance, bind each DOUT/PD_SCK pair to its own device:

```python
gpio = FakeGpio()
gpio.add_device(5, 6, FakeHx711())
gpio.add_device(7, 8, FakeHx711())

hx_a = HX711(5, 6, gpio_module=gpio)
hx_b = HX711(7, 8, gpio_module=gpio)
```

The emulator is intended for software testing, not for validating real timing.
It currently supports only channel A gain 128; selecting channel B gain 32 or
channel A gain 64 raises an error in the emulator. See the
[emulator review](emulator-review.md) for implementation details and known
limitations.
