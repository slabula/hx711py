# HTTP server

`hx711_server.py` reads the HX711 in a background thread and serves up to the
latest 100 calibrated readings as JSON over HTTP:

```bash
python hx711_server.py --unit kg --m 0.000018 --c -2.5
```

Then poll it from another machine:

```bash
python example_client.py --url http://raspberrypi.local:8080/weight
```

The client also prints the sample rate estimated from the server's `samples`
list. It uses all sample timestamps, so repeated `weight` values still count as
samples. Servers that do not provide samples show `rate n/a`.

Use `--csv FILE` to append `timestamp,weight` rows to a CSV file:

```bash
python example_client.py --url http://raspberrypi.local:8080/weight --csv samples.csv
python example_client.py --serial /dev/ttyACM0 --unit kg --csv samples.csv
```

The file gets a `timestamp,weight` header when it is created. HTTP mode writes
each history sample once even though consecutive polls overlap; serial mode
writes every valid line as received.

`GET /weight` (or `GET /`) returns:

```json
{
  "ts": 1794601083.345,
  "weight": 12.47,
  "unit": "kg",
  "samples": [
    {"ts": 1794601082.912, "weight": 12.31, "unit": "kg"},
    {"ts": 1794601083.345, "weight": 12.47, "unit": "kg"}
  ]
}
```

The top-level fields still describe the latest reading, so existing clients keep
working. `samples` contains up to 100 readings, oldest first.

| Field | Meaning |
| --- | --- |
| `ts` | UTC epoch seconds |
| `weight` | Calibrated reading, filtered if enabled |
| `unit` | Unit label |
| `samples` | Up to 100 recent reading objects with `ts`, `weight`, and `unit` |

The server returns `503` until the first reading is available. It has no
authentication, so only expose it on a trusted network.

## Server options

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8080` | TCP port |
| `--dout` | `5` | DOUT GPIO pin |
| `--pd-sck` | `6` | PD_SCK GPIO pin |
| `--gpio` | `rpi` | GPIO backend: `rpi` or `pigpio` |
| `--gain` | `128` | Channel A gain 128/64, or channel B gain 32 |
| `--m` | `1.0` | Calibration `m` |
| `--c` | `0.0` | Calibration `c` |
| `--unit` | `units` | Unit label reported to clients |
| `--serial` | disabled | Also stream `timestamp,weight` lines to this device |
| `--serial-baudrate` | `115200` | Serial baud rate (ignored by USB ACM) |
| `--filter` | automatic | `none`, `median`, `ema`, `median-ema`, `hampel`, or `hampel-ema` |
| `--filter-cutoff` | disabled | Low-pass cutoff in Hz for `ema`, `median-ema`, and `hampel-ema` |
| `--filter-sample-rate` | `80` | Expected sample rate for filtering, in Hz |
| `--filter-window`, `--filter-median-window` | `5` | Window size for median-based filters |
| `--filter-mad-threshold` | `3.0` | Hampel MAD threshold |
| `--filter-mad-scale` | `1.4826` | Hampel MAD scale factor |
| `--filter-min-mad` | `0` | Absolute minimum Hampel rejection limit |

## Filtering

Select a filter with `--filter`:

```bash
# Pure median, no low-pass smoothing
python hx711_server.py --filter median --filter-window 5

# Exponential low-pass only
python hx711_server.py --filter ema --filter-cutoff 5 --filter-sample-rate 80

# Original median + EMA behavior
python hx711_server.py --filter median-ema --filter-cutoff 5 --filter-sample-rate 80

# Hampel outlier rejection followed by EMA
python hx711_server.py --filter hampel-ema --filter-cutoff 5 \
  --filter-window 7 --filter-mad-threshold 3.0
```

For compatibility, supplying `--filter-cutoff` without `--filter` still selects
`median-ema`. Without a filter and without `--filter-cutoff`, readings are
unfiltered. Set `--filter-sample-rate` to the actual read rate for your
hardware. See [API reference](api.md#filtering) for the Python filter classes.

## Related guides

- [USB serial streaming](usb-serial.md) — stream `timestamp,weight` lines over a Pi Zero W USB gadget port.
- [Emulator](emulator.md) — test client code without hardware using fake GPIO/HX711 classes.
- [USB serial streaming](usb-serial.md#run-the-server-at-boot) — start the server automatically with systemd.
