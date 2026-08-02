# esphome-matter
ESPHome external component adding Matter 1.5 support via Espressif's [esp-matter 1.5.1](https://components.espressif.com/components/espressif/esp_matter/versions/1.5.1).

> [!WARNING]
> This project is still in early-development so don't expect a perfectly working setup. matter-over-wifi is now sort
> of working but only very few matter endpoints are supported yet. Currently only the `on_off_switch`, `dimmer_switch`,
> `temperature_sensor`, `on_off_light` and `dimmable_light` endpoints are supported.
> I will first focus on matter-over-thread and matter-over-ethernet and getting everything stable before I add useful features.

# Contributing

Help is very welcome! I'm not deeply experienced in the ESPHome, Espressif, or connectedhomeip ecosystems. If you know your way around any of these and spot something wrong or have ideas, please open an issue or PR.

Even if you have no experience with any of these: just building the project and confirming (or reporting) whether it works on your setup is genuinely useful. [Open an issue](https://github.com/DavidvtWout/esphome-matter/issues) if something doesn't work or create or join a [discussion](https://github.com/DavidvtWout/esphome-matter/discussions) if you have feature requests or ideas.

# Progress

- matter-over-wifi: Working now! If you have configured `wifi` in the device config, matter announces itself via mDNS and you can commission it over-the-network.
- matter-over-thread: The next step will be supporting the `openthread` component.
- matter-over-ethernet: Not sure. But probably doesn't work yet.
- commissioning over BLE: If no network (`wifi`, `openthread`, `ethernet`) is configured at all, matter falls back to 
  BLE commissioning. This is how almost every matter device is commissioned. This mode is currently not compatible with
  the `api` component since this checks network connectivity in a rather naive way that always fails if no network is
  configured. This bug can only be fixed in ESPHome itself.
- binding: Binding (for example a button to a light) requires matter devices to find each other via dns-sd. This is not yet working.

See the [issue page](https://github.com/DavidvtWout/esphome-matter/issues) for more planned features.

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
  # Native esp-idf isn't supported yet.
  toolchain: platformio
  variant: ESP32C6 # Set to your variant
  framework:
    type: esp-idf

external_components:
  - source: github://DavidvtWout/esphome-matter@main

logger:
  
api:
  
network:
  enable_ipv6: true
  
wifi:
  ...

matter:
  endpoints:
    - dimmer_switch:
      id: dimmer_endpoint
    - temperature_sensor:
        sensor_id: internal_temp
    - on_off_light:
        light_id: user_led

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

output:
  # On a Seeed Studio XIAO ESP32-C6, the GPIO15 pin is wired to the user LED. Pick
  # the correct pin for your board or remove the `output` and `light` sections.
  - platform: gpio
    pin:
      number: GPIO15
      inverted: true
    id: user_led_pin

light:
  - platform: binary
    name: "User LED"
    output: user_led_pin
    id: user_led
    # It's recommended to set `internal: true` for lights, since this hides the entity from
    # Home Assistant. Without it, both HA and matter try to own the light's state. If both
    # issue a command at nearly the same time, they enter a feedback loop and the light
    # toggles on/off indefinitely.
    internal: true
```
