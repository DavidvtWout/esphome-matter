# Ethernet development and testing

Ethernet support is experimental. Startup, on-network discovery, Apple Home
commissioning, and temperature data delivery have been validated on one Waveshare
ESP32-P4-Module-DEV-KIT revision-1 board. Reboot and cable recovery still need
validation.
ESPHome owns the Ethernet driver and network interface; Matter uses that interface
for on-network commissioning, discovery, and communication. The integration overrides
the bundled SDK's Ethernet commissioning initialization to avoid installing a
second driver, and preserves the Ethernet IPv4 event payload that this SDK omits.
These workarounds are specific to the bundled SDK and should be reviewed when that
dependency changes. The same SDK's CMake source selection excludes its ESP32
DNS-SD backend when Wi-Fi is disabled. `matter_ethernet_dnssd.cpp` compiles that
bundled source for Ethernet-only builds; remove this workaround once the SDK
includes the backend for Ethernet itself.

Configure the ESPHome `ethernet:` component for your board and enable IPv6:

```yaml
network:
  enable_ipv6: true
```

The [compile fixture](../tests/configs/esp32-ethernet.yaml) targets the Waveshare
ESP32-P4-Module-DEV-KIT with its onboard IP101GRI PHY and a temperature endpoint.
The P4 runs ESPHome and Matter; the C6 wireless coprocessor is not needed for this
Ethernet-only configuration. Board wiring is documented in the
[Waveshare Ethernet demo](https://www.waveshare.com/wiki/ESP32-P4-Module-DEV-KIT-StartPage).
The configuration uses MDC GPIO31, MDIO GPIO52, PHY reset GPIO51, and external
RMII clock GPIO50. PHY address 1 follows the IP101 configuration for Waveshare P4
boards in the [ESPHome device guide](https://devices.esphome.io/devices/waveshare-esp32-p4-eth/);
confirm it against your board revision if the PHY fails to initialize.

A [local development example](../examples/waveshare-esp32-p4-ethernet.yaml) is also
provided. It uses the component from this checkout. The equivalent CI fixture
was built and flashed over USB for the startup and discovery checks below. USB chip identification confirmed revision 1.0 on the
development board, so the example sets `esp32.engineering_sample: true` and
uses a 360 MHz CPU clock. For production revision-3 boards, set
`engineering_sample: false` instead. The P4 example targets ESPHome 2026.8.2.

With Ethernet configured, the component disables the fallback Wi-Fi, Thread, and
BLE commissioning configuration. Use the setup code from the device logs to
commission on the local network, as described in the main README.

## Development validation

- ESPHome 2026.8.2: revision-1 P4 Ethernet firmware compiled and linked successfully.
- Final link map: Ethernet initialization resolves to `matter_ethernet_stack.cpp`;
  the Ethernet IPv4 event wrapper and DNS-SD backend are present in the firmware.
- Wi-Fi and Thread configurations validate and generate code without the Ethernet
  event wrapper; the all-endpoints configuration also validates.
- USB inspection identified the attached development board as ESP32-P4 revision 1.0.
- Firmware flashed over USB with upload hash verification, then booted successfully.
- Ethernet negotiated 100 Mbps full duplex, acquired its DHCP address, and created
  an IPv6 link-local address.
- Matter logged `Using ESPHome Ethernet interface`, `Server ready!`, and an open
  commissioning window; macOS independently resolved its `_matterc._udp` service
  on port 5540.
- User-provided Apple Home screenshots on 2026-09-15 confirm commissioning and
  a displayed temperature of 27.5° for the Ethernet accessory. This endpoint uses
  the ESP32 internal temperature sensor, not an ambient room sensor. Controller
  OS version and ongoing subscription updates have not been independently verified.
- Post-commissioning reboot and cable recovery remain untested.

## Validation before claiming hardware support

Record the board, PHY/controller, ESPHome version, and Matter controller version.
Verify:

- IPv6 address assignment and Matter discovery on the Ethernet interface.
- Initial commissioning and endpoint reads or commands.
- Reboot with the existing fabric retained and control restored.
- Cable removal and reconnection, followed by discovery and control recovery.
- Boot without a cable, then connect it and commission or control the device.
- Matter factory reset and recommissioning.

CI validates the Ethernet configuration and includes it in the pull-request
compile matrix alongside Wi-Fi and Thread. A successful build does not establish
hardware support; add actual device results here when available.
