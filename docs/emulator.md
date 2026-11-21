# Emulator

When `RPi.GPIO` is unavailable, the library automatically uses `FakeGpio` and
`FakeHx711`, so imports and examples still work. `example_emulator.py` shows how
to inject your own samples:

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

The emulator is intended for software testing, not for validating real timing.
It currently supports only channel A gain 128; selecting channel B gain 32 or
channel A gain 64 raises an error in the emulator. See the
[emulator review](emulator-review.md) for implementation details and known
limitations.
