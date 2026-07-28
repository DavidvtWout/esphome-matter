# esphome-matter
ESPHome external component for matter support.

It's still in early-development. Currently only the `on_off_switch`, `dimmer_switch`, `temperature_sensor`,
`on_off_light` and `dimmable_light` matter endpoints are supported.

# Progress

- matter-over-wifi: Working now! If you have configured `wifi` in the device config, matter announces itself via mDNS and you can commission it over-the-network.
- matter-over-thread: The next step will be supporting the `openthread` component.
- matter-over-ethernet: Not sure. But probably doesn't work yet.
- commissioning over BLE: If no network (`wifi`, `openthread`, `ethernet`) is configured at all, matter falls back to 
  BLE commissioning. This is how almost every matter device is commissioned. This mode is currently not compatible with
  the `api` component since this checks network connectivity in a rather naive way that always fails if no network is
  configured. This bug can only be fixed in ESPHome itself.

# Compilation

esphome-matter requires the esp-idf framework. The arduino framework won't work. Since esphome 2026.1.0 this is the
default anyway, but if you're still on an earlier version you need to specify the framework;

```yaml
esp32:
  framework:
    type: esp-idf
```

# Commissioning

Directly after flashing ESPHome (and after every restart), the commissioning code (starting with `MT:`) is printed in the logs:
```
[C][matter:293]: Matter:
[C][matter:314]:   SetupQRCode: MT:Y.K904QI14-O992WI00
[C][matter:315]:   QR URL: https://project-chip.github.io/connectedhomeip/qrcode.html?data=MT:Y.K904QI14-O992WI00
[C][matter:323]:   Manual pairing code: 32552014321
[C][matter:328]:   Commissioning window: open
[C][matter:332]:   Fabrics: none
```

Copy the code and use this to commission the device. In python-matter-server you can commission the device with the `Commission existing device` option.
Keep in mind that the commissioning window remains open for only 15 minutes. A restart of the device will re-open the window but only if it hasn't joined any fabrics yet.

# Example config

```yaml
esphome:
  name: matter-device
  friendly_name: Matter Device

esp32:
  framework:
    variant: ESP32C6
    type: esp-idf

external_components:
  - source: github://DavidvtWout/esphome-matter@main
    refresh: 0s

logger:
  
api:
  
network:
  enable_ipv6: y
  
wifi:
  ...

matter:
  endpoints:
    - dimmer_switch:
      id: dimmer_endpoint 
    - temperature_sensor:
        sensor_id: internal_temp

# The two buttons are configured to be triggered when the GPIO pin is pulled down to GND.
binary_sensor:
  - name: "Button up"
    platform: gpio
    pin:
      number: GPIO0
      mode:
        pullup: true
        input: true
      inverted: true
    on_click:
      matter.turn_on:
        id: dimmer_endpoint
    on_press:
      matter.dim_up:
        id: dimmer_endpoint
    on_release:
      matter.dim_stop:
        id: dimmer_endpoint
  - name: "Button down"
    id: button_down
    platform: gpio
    pin:
      number: GPIO1
      mode:
        pullup: true
        input: true
      inverted: true
    on_click:
      matter.turn_off:
        id: dimmer_endpoint
    on_press:
      matter.dim_down:
        id: dimmer_endpoint
    on_release:
      matter.dim_stop:
        id: dimmer_endpoint

sensor:
  - platform: internal_temperature
    name: "Internal Temperature"
    id: internal_temp
```
