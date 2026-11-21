# Emulator and CSV replay

## Hardware-free emulator

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

## Replay fake data from CSV

`dummy_scale_server.py` in the repository root replays a two-column
`timestamp,weight` CSV through the same `GET /weight` payload as
`hx711_server.py`, so you can test HX711 JSON clients without hardware:

```bash
python3 dummy_scale_server.py live.csv --loop --start-delay 5
```

Timestamps are scheduling marks in seconds; relative and epoch timestamps both
work because only differences matter. Use `--speed` to compress long files.
Add a few seconds of zero load at the start of the CSV if the session should
begin from rest. When the file ends the last reading is held; `--loop` repeats
it. `--start-delay` holds the first reading while clients connect and tare.

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8080` | TCP port |
| `--unit` | `kg` | Unit label |
| `--speed` | `1.0` | Replay speed multiplier |
| `--loop` | off | Restart the file when it ends |
| `--start-delay` | `0` | Hold the first reading for this many seconds |

See [HTTP server](server.md) for the payload format and HTTP client usage.
