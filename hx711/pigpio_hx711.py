import threading
import time

from .core import HX711, twos_complement_24bit_to_int


_DATA_BITS = 24
_PULSE_LENGTH_US = 15
_SETTLE_READINGS = 5


class PigpioGpio:
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"

    def __init__(self, pi, pigpio_module):
        self._pi = pi
        self._input_mode = pigpio_module.INPUT
        self._output_mode = pigpio_module.OUTPUT

    def setmode(self, mode):
        if mode != self.BCM:
            raise ValueError("pigpio only supports BCM pin numbering")

    def setup(self, pin, direction):
        if direction == self.OUT:
            self._pi.set_mode(pin, self._output_mode)
            return

        if direction == self.IN:
            self._pi.set_mode(pin, self._input_mode)
            return

        raise ValueError("setup({}, {})".format(pin, direction))

    def output(self, pin, value):
        self._pi.write(pin, 1 if value else 0)

    def input(self, pin):
        return self._pi.read(pin)

    def cleanup(self):
        pass


class PigpioHX711(HX711):
    def __init__(self, dout, pd_sck, pi=None, pigpio_module=None, close_pi=None):
        if pigpio_module is None:
            try:
                import pigpio as pigpio_module
            except ImportError as exc:
                raise ImportError(
                    "PigpioHX711 requires the pigpio package and a running pigpiod"
                ) from exc

        owns_pi = pi is None if close_pi is None else close_pi

        if pi is None:
            pi = pigpio_module.pi()

        if not getattr(pi, "connected", True):
            raise RuntimeError("pigpio daemon is not connected")

        self._pi = pi
        self._pigpio = pigpio_module
        self._owns_pi = owns_pi
        self._closed = False
        self._read_event = threading.Event()
        self._read_active = False
        self._result = None
        self._clock_count = 0
        self._expected_clocks = 0
        self._value = 0
        self._data_level = 0
        self._settle_readings = 0
        self._waves = {}
        self._callbacks = []

        super().__init__(dout, pd_sck, gpio_module=PigpioGpio(pi, pigpio_module))

        try:
            self._pi.write(self._pd_sck, 0)
            self._create_waves()

            data_callback = self._pi.callback(
                self._dout, pigpio_module.EITHER_EDGE, self._on_data
            )
            if data_callback is None:
                raise RuntimeError("could not register pigpio data callback")
            self._callbacks.append(data_callback)

            clock_callback = self._pi.callback(
                self._pd_sck, pigpio_module.FALLING_EDGE, self._on_clock
            )
            if clock_callback is None:
                raise RuntimeError("could not register pigpio clock callback")
            self._callbacks.append(clock_callback)
        except Exception:
            self.cleanup()
            raise

    def _create_waves(self):
        clock_mask = 1 << self._pd_sck

        for extra_clocks in (
            self.CH_A_GAIN_128,
            self.CH_B_GAIN_32,
            self.CH_A_GAIN_64,
        ):
            pulses = []
            for _ in range(_DATA_BITS + extra_clocks):
                pulses.append(
                    self._pigpio.pulse(clock_mask, 0, _PULSE_LENGTH_US)
                )
                pulses.append(
                    self._pigpio.pulse(0, clock_mask, _PULSE_LENGTH_US)
                )

            self._pi.wave_add_generic(pulses)
            wave_id = self._pi.wave_create()
            if wave_id < 0:
                raise RuntimeError(
                    "pigpio wave_create failed with code {}".format(wave_id)
                )

            self._waves[extra_clocks] = wave_id

    def _on_data(self, gpio, level, tick):
        if self._read_active and level in (0, 1):
            self._data_level = level

    def _on_clock(self, gpio, level, tick):
        if not self._read_active or level != 0:
            return

        self._clock_count += 1

        if self._clock_count <= _DATA_BITS:
            self._value = ((self._value << 1) | (self._data_level & 1)) & 0xFFFFFF

        if self._clock_count >= self._expected_clocks:
            self._result = twos_complement_24bit_to_int(self._value)
            self._read_active = False
            self._read_event.set()

    def _wait_for_wave_idle(self, wave_id, deadline):
        wave_busy = getattr(self._pi, "wave_busy", None)
        if wave_busy is None:
            return True

        while wave_busy(wave_id):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.00005)

        return True

    def _read_word_once(self, timeout_seconds):
        if self._closed:
            raise RuntimeError("PigpioHX711 has been cleaned up")

        deadline = time.monotonic() + timeout_seconds

        while self._pi.read(self._dout) != 0:
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.0001)

        wave_id = self._waves[self._gain]

        if not self._wait_for_wave_idle(wave_id, deadline):
            return None

        self._read_event.clear()
        self._result = None
        self._clock_count = 0
        self._expected_clocks = _DATA_BITS + self._gain
        self._value = 0
        self._data_level = 1 if self._pi.read(self._dout) else 0
        self._read_active = True

        try:
            self._pi.wave_send_once(wave_id)
        except Exception:
            self._read_active = False
            raise

        if not self._read_event.wait(max(0.0, deadline - time.monotonic())):
            self._read_active = False
            return None

        return self._result

    def read_word(self, timeout_seconds=0.5):
        with self._read_lock:
            deadline = time.monotonic() + timeout_seconds

            while self._settle_readings > 0:
                raw_sample = self._read_word_once(
                    max(0.0, deadline - time.monotonic())
                )
                if raw_sample is None:
                    return None
                self._settle_readings -= 1

            return self._read_word_once(max(0.0, deadline - time.monotonic()))

    def set_channel_gain(self, enum_value):
        with self._read_lock:
            super().set_channel_gain(enum_value)
            self._settle_readings = _SETTLE_READINGS

    def cleanup(self):
        with self._read_lock:
            if self._closed:
                return

            self._closed = True
            self._read_active = False

            for callback in self._callbacks:
                callback.cancel()
            self._callbacks = []

            for wave_id in self._waves.values():
                self._pi.wave_delete(wave_id)
            self._waves = {}

            self._gpio.cleanup()

            if self._owns_pi:
                self._pi.stop()
