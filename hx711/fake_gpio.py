#! /usr/bin/python3


class FakeGpio:
    """Fake RPi.GPIO module for testing without hardware.

    Pin state is tracked per pin so several HX711 instances can share one
    FakeGpio. Each DOUT/PD_SCK pair can be bound to its own FakeHx711 with
    add_device(); pins without an explicit binding use the default device
    passed to the constructor.
    """

    BCM = "UseBroadcomNumbering"
    BOARD = "UsePhysicalBoardNumbering"
    OUT = "fake_gpio_output"
    IN = "fake_gpio_input"

    def __init__(self, fake_hx711=None):
        self._default_device = fake_hx711
        self._pin_devices = {}
        self._input_pins = set()
        self._output_pins = set()

    def add_device(self, dout_pin, pd_sck_pin, fake_hx711):
        """Bind one DOUT/PD_SCK pin pair to a FakeHx711 device."""
        self._pin_devices[dout_pin] = fake_hx711
        self._pin_devices[pd_sck_pin] = fake_hx711

    def _device_for(self, pin):
        device = self._pin_devices.get(pin)
        if device is not None:
            return device

        if self._default_device is not None:
            return self._default_device

        raise ValueError("no fake HX711 registered for pin {}".format(pin))

    def setmode(self, value):
        assert value in [self.BCM, self.BOARD]

    def setup(self, pin, value_b):
        if value_b == self.OUT:
            self._input_pins.discard(pin)
            self._output_pins.add(pin)
            return

        if value_b == self.IN:
            self._output_pins.discard(pin)
            self._input_pins.add(pin)
            return

        raise ValueError("setup({}, {})".format(pin, value_b))

    def output(self, pin, value):
        if pin not in self._output_pins:
            raise ValueError("output({}, {})!! Not setup as an output!".format(pin, value))

        self._device_for(pin).set_pd_sck(value)

    def input(self, pin):
        if pin not in self._input_pins:
            raise ValueError("input({})!! Not setup as an input!".format(pin))

        return self._device_for(pin).dout()

    def cleanup(self):
        self._input_pins.clear()
        self._output_pins.clear()


# EOF - fake_gpio.py
