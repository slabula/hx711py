# HX711 Emulator Review

Review of the emulator implementation in:

- `hx711/fake_hx711.py`
- `hx711/fake_gpio.py`
- `example_emulator.py`

## Verdict

The emulator is largely correct for the supported path: Channel A, Gain 128.

Verified behaviour:

- 24-bit MSB-first data is returned correctly, including two's complement
  negatives. Injected `0, 1, 2, 3, -1` read back as `0, 1, 2, 3, -1`.
- The bit selected on a rising edge remains stable through the falling edge,
  so `HX711.read_word()`'s sample-after-falling-edge logic works.
- The 25th pulse raises DOUT back to high.
- Reset/power-up schedules a new sample and selects Channel A, Gain 128.
- DOUT is high while no sample is ready and while powered down.
- `FakeGpio` correctly maps the single DOUT/PD_SCK pin pair used by `HX711`.

The main issues are in power-down handling and rejected gain selections.

## Priority Summary

| Priority | Issue |
| --- | --- |
| P1 | Unsupported gains fail on a later, alternating read and consume samples |
| P2 | Injected samples behave as a FIFO instead of a single result register |
| P3 | Initial power state does not match power-up behaviour |
| P3 | Minor comment/dead-code/range issues |

## P1: Unsupported Gain Rejection Is Delayed and Intermittent

Location: `hx711/fake_hx711.py:160-182`

`next_sample()` mutates state before validating the selected gain:

- `:163-164` pops a pending sample and assigns `_raw_value`.
- `:166-170` resets the clock counts and marks the sample ready.
- `:176-182` raises for 26 or 27 clocks (Channel B Gain 32 / Channel A Gain 64).

As a result, `HX711.set_channel_gain()` returns successfully because its
discard read still clocks out the previous Channel A sample. The error appears
on a later read, and because the counts were reset before raising, the following
read succeeds. Reads then alternate between raising and returning values.
`is_ready()` can raise as well.

Reproduction:

```python
from hx711 import HX711
from hx711.fake_hx711 import FakeHx711
from hx711.fake_gpio import FakeGpio

fake = FakeHx711()
fake.inject_raw_samples(list(range(10)))
hx = HX711(5, 6, gpio_module=FakeGpio(fake))
hx.reset()
hx.set_channel_gain(HX711.CH_A_GAIN_64)  # returns normally

for _ in range(6):
    try:
        print(hx.read_word())
    except ValueError as exc:
        print("raised:", exc)
```

Observed output:

```text
raised: Channel A Gain 64 not supported, yet!
1
raised: Channel A Gain 64 not supported, yet!
2
raised: Channel A Gain 64 not supported, yet!
3
```

Note that the injected sample is consumed on each raising read.

Suggested fix, in order of preference:

1. Implement Channel A Gain 64 and Channel B Gain 32 in the emulator. The fake
   can reuse the same raw samples, or use `REFERENCE_B_UNIT` when converting
   injected floating-point samples.
2. If those gains must remain unsupported, validate before popping a sample or
   setting `_sample_ready`, and latch the invalid selection so every subsequent
   read fails deterministically until the selection is changed.

## P2: FIFO Instead of a Single Result Register

Location: `hx711/fake_hx711.py:108-110`, `:160-164`

`_pending_value_list` is consumed one value per conversion. If the caller reads
more slowly than 80 SPS, the emulator still returns every injected value in
order instead of skipping values like the real chip, whose result register is
overwritten by newer conversions.

Reproduction:

```python
import time
from hx711 import HX711
from hx711.fake_hx711 import FakeHx711
from hx711.fake_gpio import FakeGpio

fake = FakeHx711()
fake.inject_raw_samples(list(range(10)))
hx = HX711(5, 6, gpio_module=FakeGpio(fake))
hx.reset()

for _ in range(4):
    time.sleep(0.05)
    print(hx.read_word())  # prints 0, 1, 2, 3
```

At 80 SPS, a 50 ms gap covers about four conversions, so a real chip would skip
ahead rather than returning the next queued value.

This may be intentional for deterministic tests. If so, document it as FIFO
test-injection behaviour. If realistic timing is wanted, drop stale pending
values based on the number of elapsed conversion periods and keep only the
latest.

## P3: Initial Power State

Location: `hx711/fake_hx711.py:105-106`

The emulator starts with `_powered_down = True` and `_pd_sck_value = True`.
The datasheet comments in the same file (`:71-88`) say power-up/reset defaults
to normal operation, Channel A, Gain 128.

Practical effect:

- `is_ready()` never becomes ready before the first write, because it only reads
  DOUT and the emulator stays powered down.
- `read_word()` and `reset()` mask this because they drive PD_SCK low, which
  wakes the emulator.

Consider starting with `_powered_down = False`, `_pd_sck_value = False`, and a
first conversion scheduled. Alternatively, document that `reset()` is required
before use. The current state is not fatal, but it is not faithful to power-up.

## P3: Minor Issues

- `:95` comment says `0.0125ms`; the constant is `0.0125` seconds, i.e. 12.5 ms.
- `:116` `_prev_clock_count` is assigned in `__init__` but never used.
- `:118-124` `inject_float_samples()` always uses `REFERENCE_A_UNIT`, ignores
  the otherwise unused `REFERENCE_B_UNIT`, and truncates with `int()` rather
  than rounding.
- Injected raw values are not range-checked or saturated. The real HX711
  saturates at `0x7FFFFF` / `0x800000`, as noted at `:15-18`.
- `:186` prints `Unrecognised clock count!` from library code; a warning or
  logging call would be less noisy.
- No tests currently exercise `FakeHx711` or `FakeGpio`. `tests/test_core.py`
  defines its own fakes, so these emulator bugs are not covered.

## Suggested Test Cases

- Inject positive, zero, and negative 24-bit samples and verify read-back.
- Verify the 25th/26th/27th pulse behaviour and the resulting gain selection.
- Verify that powering down for several sample periods does not consume
  pending samples.
- Verify deterministic behaviour after selecting an unsupported gain.
- Verify the documented FIFO behaviour, or the overwrite behaviour if changed.
- Verify `is_ready()` behaviour before and after the first conversion.
