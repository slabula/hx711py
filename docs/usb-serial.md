# USB serial streaming

A Pi Zero W can act as a **USB gadget**: instead of being a USB host, it presents
itself to a PC as a peripheral. This lets `hx711_server.py --serial /dev/ttyGS0`
stream readings over a plain USB cable as `timestamp,weight` lines.

This applies to the Pi Zero, Zero W, Zero 2 W, and Pi 3 Model A+. Pi 4/5 can
also do gadget mode, but use their USB-C port and the ConfigFS method below.
Pi 3B/3B+ and older models cannot do USB gadget mode.

The HTTP endpoint keeps running at the same time; see [HTTP server](server.md).

## Which port to use

The Zero W has two micro-USB sockets:

| Port | Purpose |
| --- | --- |
| `USB` / `OTG` (the one closest to the mini-HDMI port) | USB data; use this one for gadget mode |
| `PWR IN` | Power only; no USB data lines |

Plug a standard USB A-to-micro-B cable from your PC into the port labeled
`USB`, **not** `PWR IN`. The two ports share the same 5 V rail, so the Pi can
usually be powered from the host through the data port. Use a single power
source: if you also power `PWR IN` from an external supply, the two supplies can
feed into each other. If the host port is too weak, use a powered USB hub or a
USB Y-cable that separates data and power.

Because the USB port becomes a device port, you cannot use it for a keyboard or
mouse at the same time. Use Wi-Fi/SSH to administer the Pi.

## Method 1: legacy `g_serial` (simplest)

Update the OS first:

```bash
sudo apt update
sudo apt full-upgrade
sudo reboot
```

Raspbian 9 (Stretch) is end-of-life, so `apt update` may fail until you point
`/etc/apt/sources.list` at the archived repositories (`archive.raspbian.org`).
You do not have to upgrade the OS for the serial gadget to work; Stretch's 4.x
kernel includes `g_serial`.

Enable the DWC2 device-mode overlay. On Raspberry Pi OS Bookworm and newer,
the boot files live in `/boot/firmware`; on **Raspbian Stretch use `/boot`**:

```bash
# Raspbian 9 (Stretch)
sudo nano /boot/config.txt

# Bookworm and newer
sudo nano /boot/firmware/config.txt
```

Add this line:

```text
dtoverlay=dwc2
```

Then load the gadget driver. Either append the following to the single-line
`cmdline.txt` — `/boot/cmdline.txt` on Stretch, `/boot/firmware/cmdline.txt` on
Bookworm — after `rootwait`, separated by spaces:

```text
modules-load=dwc2,g_serial
```

For example, a Stretch `cmdline.txt` should end with:

```text
... rootwait modules-load=dwc2,g_serial
```

Keep it on **one line**; `cmdline.txt` cannot contain newlines.

…or create a modules-load file instead:

```bash
printf 'dwc2\ng_serial\n' | sudo tee /etc/modules-load.d/usb-gadget.conf
```

Reboot:

```bash
sudo reboot
```

On the Pi, verify:

```bash
lsmod | grep -E 'dwc2|g_serial|usb_f_acm'
ls -l /dev/ttyGS0
```

On the host, check that a new serial device appeared:

```bash
dmesg -w            # Linux: look for "cdc_acm" / "ttyACM"
ls /dev/ttyACM*
```

Windows normally creates a COM port automatically. If Windows asks for a
driver, bind the device to the built-in `usbser.sys` driver with a small INF.

## Method 2: ConfigFS with a custom serial device

Use ConfigFS if you want a custom vendor/product ID or want to add other USB
functions later. Do **not** load `g_serial` when using this method.

Create `/etc/modules-load.d/usb-gadget.conf`:

```text
dwc2
libcomposite
```

Create `/usr/local/sbin/usb-gadget-serial.sh`:

```bash
#!/bin/sh
set -eu

modprobe libcomposite

GADGET=/sys/kernel/config/usb_gadget/hx711
UDC=$(ls /sys/class/udc | head -n 1)

mkdir -p "$GADGET"
cd "$GADGET"

echo 0x1d6b > idVendor          # Linux Foundation
echo 0x0104 > idProduct         # Multifunction Composite Gadget
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

mkdir -p strings/0x409
echo "hx711-scale-01" > strings/0x409/serialnumber
echo "Your Name" > strings/0x409/manufacturer
echo "HX711 Scale" > strings/0x409/product

mkdir -p configs/c.1/strings/0x409
echo "HX711 serial" > configs/c.1/strings/0x409/configuration
echo 120 > configs/c.1/MaxPower

mkdir -p functions/acm.usb0
ln -sfn "$GADGET/functions/acm.usb0" "$GADGET/configs/c.1/acm.usb0"

echo "$UDC" > UDC
```

Make it executable:

```bash
sudo chmod +x /usr/local/sbin/usb-gadget-serial.sh
```

Run it once to test, then make it run at boot with a systemd unit at
`/etc/systemd/system/usb-gadget-serial.service`:

```ini
[Unit]
Description=USB ACM serial gadget
After=local-fs.target
ConditionPathExists=/sys/kernel/config/usb_gadget

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/usb-gadget-serial.sh

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now usb-gadget-serial.service
```

`/dev/ttyGS0` should now exist on the Pi. Change `idVendor`, `idProduct`, and
the strings to whatever your host software expects.

## Permissions

`/dev/ttyGS0` is normally owned by `root:dialout` with mode `0660`. The default
`pi` user is in `dialout`, so no change is needed. Check with:

```bash
ls -l /dev/ttyGS0
id pi
```

If `pi` is not in `dialout`:

```bash
sudo usermod -aG dialout pi
```

Log out and back in, or reboot, for the new group to take effect. Test as the
`pi` user:

```bash
sudo -u pi python3 -c "import serial; serial.Serial('/dev/ttyGS0', 115200, write_timeout=0).close()"
```

For a systemd service running as `pi`, either rely on group membership or add:

```ini
[Service]
User=pi
Group=dialout
```

If your system does not assign `ttyGS0` to `dialout`, add a udev rule instead
of making the device world-writable:

```bash
sudo tee /etc/udev/rules.d/99-usb-gadget-serial.rules <<'EOF'
SUBSYSTEM=="tty", KERNEL=="ttyGS0", GROUP="dialout", MODE="0660"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Loading `dwc2`/`g_serial` and writing ConfigFS files needs root, but that
happens at boot via `modules-load` or a systemd unit — not through the `pi`
user.

## Common problems

| Symptom | Check |
| --- | --- |
| No `/dev/ttyGS0` on the Pi | `dtoverlay=dwc2` present, `g_serial`/`libcomposite` loaded, rebooted |
| Host sees nothing | Use the `USB` port, not `PWR IN`; try a different cable and host port; avoid docks/hubs |
| `Write timeout` on the Pi | The host must have the port open and be reading it continuously |
| Pi reboots or drops the link | Host port cannot supply enough current; use a powered hub or separate power |
| `Permission denied` opening the port | Add your user to `dialout` or run the service as root |
| A login prompt appears on the host | Disable the getty: `sudo systemctl disable --now serial-getty@ttyGS0.service` |
| Timestamps look wrong | Set the Pi's clock (Wi-Fi/NTP); the serial line carries the Pi's epoch time |

## Stream samples over USB serial

Once `/dev/ttyGS0` exists on the Pi and the host sees `/dev/ttyACM0`, install
pyserial and start the server with `--serial`:

```bash
# On Raspbian Stretch, install pip first if it is missing:
sudo apt install python3-pip
pip3 install pyserial

python3 hx711_server.py --unit kg --m 0.000018 --c -2.5 --serial /dev/ttyGS0
```

The server uses only Python 3.5-compatible syntax, so it runs on Stretch's
default Python without changes.

Each sample is written as:

```text
1794601083.345,12.47\n
```

That is the UTC epoch timestamp in seconds, a comma, the calibrated weight,
and a newline. The unit label is **not** sent; the HTTP endpoint still reports
it if you need it. Writes are best-effort: if the host is not reading, samples
are dropped rather than blocking the HX711 reader.

If you only want serial output and no network listener, use
`--host 127.0.0.1` on the Pi to keep HTTP local.

## Serial client

Read the stream on the host with a small script:

```python
import serial

with serial.Serial("/dev/ttyACM0", 115200, timeout=1) as port:
    for line in port:
        ts, weight = line.decode().strip().split(",")
        print(float(ts), float(weight))
```

Or use this repository's client in serial mode:

```bash
pip3 install pyserial
python3 example_client.py --serial /dev/ttyACM0 --unit kg
```

It prints the same timestamp/weight/sample-rate lines as in HTTP mode. The
`--unit` label is only for display; it is not sent over the wire. `--interval`
is ignored in serial mode, and `--timeout` is used as the serial read timeout.

Malformed lines are skipped rather than printed: this includes wrong field
counts, non-numeric values, `nan`/`inf`, non-positive timestamps, and partial
lines caused by a serial read timeout. The client also reopens the device if it
disappears from the host.

## Run the server at boot

Use a systemd service so the server starts on power-up and is restarted if it
exits. An example unit is provided at
[`resources/hx711-server.service.example`](../resources/hx711-server.service.example).
Copy it, edit the path and calibration values, then enable it:

```bash
sudo cp resources/hx711-server.service.example /etc/systemd/system/hx711-server.service
sudo nano /etc/systemd/system/hx711-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now hx711-server.service
```

The example uses `User=pi`, `Group=dialout`, and `Restart=always`, so if
`/dev/ttyGS0` is not ready yet the service simply retries. Install pyserial
system-wide so the service can import it:

```bash
sudo apt install python3-serial
```

Check it with:

```bash
systemctl status hx711-server.service
journalctl -u hx711-server.service -f
```

If you used the ConfigFS gadget method, uncomment the `Wants=` and `After=`
lines for `usb-gadget-serial.service` in the unit. If you don't want serial
output, remove `--serial /dev/ttyGS0` from `ExecStart`.
