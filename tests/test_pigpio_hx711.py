import pytest

from hx711 import HX711, PigpioHX711
from hx711.core import twos_complement_24bit_to_int
from hx711.pigpio_hx711 import _DATA_BITS, _PULSE_LENGTH_US


class FakePulse:
    def __init__(self, gpio_on, gpio_off, delay):
        self.gpio_on = gpio_on
        self.gpio_off = gpio_off
        self.delay = delay


class FakePigpioModule:
    INPUT = 0
    OUTPUT = 1
    EITHER_EDGE = 2
    FALLING_EDGE = 1
    pulse = FakePulse

    def __init__(self, pi):
        self.pi_instance = pi

    def pi(self):
        return self.pi_instance


class FakeCallback:
    def __init__(self, gpio, edge, func):
        self.gpio = gpio
        self.edge = edge
        self.func = func
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakePi:
    connected = True

    def __init__(self, sample=0, ready=True):
        self.sample = sample
        self.ready = ready
        self.modes = {}
        self.writes = []
        self.current_pulses = []
        self.waves = {}
        self.sent = []
        self.deleted = []
        self.callbacks = []
        self.data_gpio = None
        self.clock_gpio = None
        self.stopped = False

    def set_mode(self, gpio, mode):
        self.modes[gpio] = mode

    def write(self, gpio, level):
        self.writes.append((gpio, level))

    def read(self, gpio):
        return 0 if self.ready else 1

    def callback(self, gpio, edge, func):
        callback = FakeCallback(gpio, edge, func)
        self.callbacks.append(callback)

        if edge == FakePigpioModule.EITHER_EDGE:
            self.data_gpio = gpio
        elif edge == FakePigpioModule.FALLING_EDGE:
            self.clock_gpio = gpio

        return callback

    def wave_add_generic(self, pulses):
        self.current_pulses.extend(pulses)

    def wave_create(self):
        wave_id = len(self.waves)
        self.waves[wave_id] = self.current_pulses
        self.current_pulses = []
        return wave_id

    def wave_send_once(self, wave_id):
        self.sent.append(wave_id)
        rising_edges = sum(1 for pulse in self.waves[wave_id] if pulse.gpio_on)

        for edge_index in range(rising_edges):
            tick = 1000 + edge_index

            if edge_index < _DATA_BITS:
                bit = (self.sample >> (_DATA_BITS - 1 - edge_index)) & 1
                self._emit(self.data_gpio, FakePigpioModule.EITHER_EDGE, bit, tick)

            self._emit(
                self.clock_gpio, FakePigpioModule.FALLING_EDGE, 0, tick
            )

    def wave_busy(self, wave_id):
        return 0

    def wave_delete(self, wave_id):
        self.deleted.append(wave_id)

    def stop(self):
        self.stopped = True

    def _emit(self, gpio, edge, level, tick):
        for callback in self.callbacks:
            if (
                not callback.cancelled
                and callback.gpio == gpio
                and callback.edge == edge
            ):
                callback.func(gpio, level, tick)


def make_reader(sample=0, ready=True):
    pi = FakePi(sample=sample, ready=ready)
    pigpio_module = FakePigpioModule(pi)
    hx = PigpioHX711(5, 6, pi=pi, pigpio_module=pigpio_module)
    return hx, pi, pigpio_module


@pytest.mark.parametrize(
    "sample, expected",
    [
        (0x000000, 0),
        (0x000001, 1),
        (0x7FFFFF, 0x7FFFFF),
        (0x800000, -0x800000),
        (0xFFFFFF, -1),
    ],
)
def test_read_word_decodes_waveform_callbacks(sample, expected):
    hx, pi, pigpio_module = make_reader(sample=sample)

    assert hx.read_word() == expected
    assert pi.modes[6] == pigpio_module.OUTPUT
    assert pi.modes[5] == pigpio_module.INPUT
    assert len(pi.waves) == 3
    assert pi.sent == [hx._waves[HX711.CH_A_GAIN_128]]

    pulses = pi.waves[hx._waves[HX711.CH_A_GAIN_128]]
    assert len(pulses) == 2 * (24 + HX711.CH_A_GAIN_128)
    assert pulses[0].delay == _PULSE_LENGTH_US
    assert pulses[0].gpio_on == 1 << 6
    assert pulses[1].gpio_off == 1 << 6


def test_read_word_uses_wave_for_selected_gain():
    hx, pi, _ = make_reader(sample=0x7FFFFF)
    hx._gain = HX711.CH_A_GAIN_64

    assert hx.read_word() == 0x7FFFFF
    assert pi.sent == [hx._waves[HX711.CH_A_GAIN_64]]
    assert len(pi.waves[hx._waves[HX711.CH_A_GAIN_64]]) == 54


def test_read_word_returns_none_without_sending_wave_when_not_ready():
    hx, pi, _ = make_reader(ready=False)

    assert hx.read_word(timeout_seconds=0.01) is None
    assert pi.sent == []


def test_set_channel_gain_discards_one_reading_and_arms_settle():
    hx, pi, _ = make_reader()

    hx.set_channel_gain(HX711.CH_B_GAIN_32)

    assert hx.get_channel_gain() == HX711.CH_B_GAIN_32
    assert hx._settle_readings == 5
    assert pi.sent == [hx._waves[HX711.CH_B_GAIN_32]]


def test_cleanup_cancels_callbacks_and_deletes_waves():
    hx, pi, _ = make_reader()

    hx.cleanup()

    assert all(callback.cancelled for callback in pi.callbacks)
    assert len(pi.deleted) == 3
    assert not pi.stopped

    with pytest.raises(RuntimeError, match="cleaned up"):
        hx.read_word()


def test_cleanup_stops_pi_only_when_it_owns_it():
    pi = FakePi()
    pigpio_module = FakePigpioModule(pi)
    hx = PigpioHX711(
        5, 6, pi=None, pigpio_module=pigpio_module, close_pi=True
    )

    hx.cleanup()

    assert pi.stopped
    assert twos_complement_24bit_to_int(0xFFFFFF) == -1
