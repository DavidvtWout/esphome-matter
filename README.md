# esphome-matter

![GitHub stars](https://img.shields.io/github/stars/DavidvtWout/esphome-matter)
![GitHub forks](https://img.shields.io/github/forks/DavidvtWout/esphome-matter)
![GitHub watchers](https://img.shields.io/github/watchers/DavidvtWout/esphome-matter)

ESPHome external component adding Matter 1.5 support via Espressif's [esp-matter 1.5.1](https://components.espressif.com/components/espressif/esp_matter/versions/1.5.1).

> This project is still in early-development so don't expect a perfectly working setup. Both
> matter-over-wifi and matter-over-thread are now working. It's possible to commission a
> device to a matter controller, but many features are still missing.
>
> Treat this component as an experimental preview. It is usable for testing, but the public
> YAML interface is not stable yet: action, cluster, attribute, and endpoint names may still
> change and break existing configurations.

That being said, esphome-matter is usable now so give it a try!

# Contributing

Help is very welcome! There is a [discussion page](https://github.com/DavidvtWout/esphome-matter/discussions/47) with issues that need to be resolved before esphome-matter is considered "releasable".

Even if you have no experience with any of these: just building the project and confirming (or reporting) whether it works on your setup is genuinely useful. [Open an issue](https://github.com/DavidvtWout/esphome-matter/issues) if something doesn't work or create or join a [discussion](https://github.com/DavidvtWout/esphome-matter/discussions) if you have feature requests or ideas. 

# Supported Hardware

The component only supports `ESP32` targets built with the **ESP-IDF** framework; the Arduino framework is not
supported. It further requires the `platformio` toolchain (`esp32.toolchain: platformio`).

Connectivity depends on which ESPHome networking components are configured:

- **Matter-over-Wi-Fi**: If `wifi` is configured, Matter announces itself over mDNS and can be commissioned
  on the network.
- **Matter-over-Thread**: Requires the `openthread` component and ESPHome **2026.6.0** or newer.
- **Matter-over-Ethernet**: Isn't supported yet and isn't actively being worked on. Feel free to implement it ;)
- **BLE commissioning**: Currently broken but this is something that I want to work on. The idea is that esphome-matter falls back to BLE commissioning (the default for most matter devices) when no `wifi`, `openthread`, or `ethernet` component is configured.

Binding (for example a button to a light) is working for matter-over-thread. For matter-over-wifi it also works but might be less stable because the CASE session is sometimes dropped.

So far, `ESP32-C3`, `ESP32-C5` `ESP32-C6`, `ESP32-S3` and `ESP32-H2` have been tested and confirmed to work!

See the [issue page](https://github.com/DavidvtWout/esphome-matter/issues) for bugs and features that are being worked on.

# Compatibility with popular ecosystems 

esphome-matter based devices will show up as "uncertified test devices" in the ecosystems. This is because the devices are not certified by the Connectivity Standards Alliance (CSA) and are not part of the official Matter certification program. The devices should still be functional, but the ecosystems might inform or warn the user about the device not being certified during the commissioning process.

### ESPHome-based devices created with esphome-matter have been tested with:

- **Home Assistant (using matterjs-server)**: ✅️ Tested and working but requires enabling the "test-net DCL" option ([See Commissioning](#ecosystem-specific-settings))
- **IKEA Home Smart**: ✅️
- **Apple iOS (iPhone or iPad) and tvOS 16 (Apple TV) - "Home" app by Apple**: ✅️
- **Google Home Ecosystem (Android or Google Nest smart speakers/display) - "Google Home" app**: ❓
- **Samsung SmartThings (Station or Hub v2 and later)**: ❓
- **Amazon Alexa (Amazon Echo)** : ❓
- **OpenHAB - Matter Binding** (openHAB Matter Client in openHAB 5.0): ❓
- **Homey Pro**: ❓
- **LG ThinQ**: ❓
- **Tuya Smart (SmartLife) app**: ❓
- **Aqara Hubs**: ❓
- **Flic**: ❓
- **Yandex Smart Home**: ❓ (and for reference; Yandex is known to not allow pairing any Matter test devices)

Please [report](https://github.com/DavidvtWout/esphome-matter/discussions/44)! any outdated or newly discovered information on compatible ecosystems, devices, and device types or issues.

# Commissioning

Because ESPHome devices already have their Wi-Fi or Thread credentials from your YAML configuration, commissioning
works differently than with most other Matter devices. You still need to commission the device to a Matter fabric, but this does not happen over BLE (bluetooth) like with most matter devices.

After flashing, the device prints a setup code (`SetupQRCode`) to the logs on every boot:

```
[C][matter]: Matter:
[C][matter]:   SetupQRCode: MT:Y.K904QI14-O992WI00
[C][matter]:   QR URL: https://project-chip.github.io/connectedhomeip/qrcode.html?data=MT:Y.K904QI14-O992WI00
[C][matter]:   Manual pairing code: 32552014321
[C][matter]:   Commissioning window: open
[C][matter]:   Fabrics: none
```

Copy the `SetupQRCode` or open the link and scan the QR-code to commission the device.

Keep in mind that the commissioning window remains open for only 15 minutes. A restart of the device will re-open the window if it hasn't joined any fabrics yet.


### Ecosystem specific settings

- **Home Assistant / matterjs server**: Start the matterjs-server with: `matterjs-server --enable-test-net-dcl=true`. Commission the device with the `Commission existing device` option.
- **Home Assistant Matter app (HA-OS only)**: Check the "Enable test-net DCL usage" box under Settings -> Apps -> Matter Server -> Configuration. If you do not do this, pairing will fail.

So far, **IKEA Home smart**, **Apple Home** and the **Android Matter Commissioning API** have been confirmed to accept commissioning right away.


# Example config

```yaml
esphome:
  name: matter-device

esp32:
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
  
# Either:
wifi:
  ...
# Or:
openthread:
  ...

matter:
  # vendor and product name can be at most 32 characters.
  # vendor_name: defaults to ESPHome
  # product_name: defaults to esphome.name
  
  # Endpoint order is significant: each entry is assigned an endpoint ID based on its position
  # in the list. Once a device has been commissioned, existing entries should not be removed
  # or reordered or the Matter fabric may lose track of previously bound endpoints.
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
      matter.on_off.on: dimmer_endpoint
    on_press:
      matter.level_control.move_with_on_off:
        endpoint_id: dimmer_endpoint
        move_mode: 0 # Move up
        rate: 50  # ~20% per second
    on_release:
      matter.level_control.stop_with_on_off: dimmer_endpoint
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
      matter.on_off.off: dimmer_endpoint
    on_press:
      matter.level_control.move_with_on_off:
        endpoint_id: dimmer_endpoint
        move_mode: 1 # Move down
        rate: 50  # ~20% per second
    on_release:
      matter.level_control.stop_with_on_off: dimmer_endpoint

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

# Actions

See [docs/actions.md](./docs/actions.md) for a more complete overview of available actions.


### OnOff cluster

OnOff commands are used for simple binary devices such as lights, plugs and relays.

```yaml
# Turn off, turn on, or toggle a bound device.
matter.on_off.off: some_id
matter.on_off.on: some_id
matter.on_off.toggle: some_id

# Intended for motion sensors temporarily turning on a light.
matter.on_off.on_with_timed_off:
  endpoint_id: some_id
  on_time: 150  # How long to turn on the light in multiples of 100ms. So 150 means 15 seconds.
  # on_off_control: 
  # off_wait_time:  # Time before accepting another on_with_timed_off command, in multiples of 100ms.
```

### LevelControl cluster

LevelControl commands are used for dimming. Levels are raw Matter brightness levels, normally `0` to `254`.

The following commands also have a version without `_with_on_off`. These commands don't turn on or off the light so that's usually not what you want.

```yaml
# Move directly to a brightness level.
matter.level_control.move_to_level_with_on_off:
  endpoint_id: some_id
  level: 128
  # transition_time:  # In multiples of 100ms. So 10 means 1 second.

# Move continuously up or down.
matter.level_control.move_with_on_off:
  endpoint_id: some_id
  move_mode: 0  # 0=up, 1=down.
  # rate:  # Level units per second.

# Step once by a fixed amount.
matter.level_control.step_with_on_off:
  endpoint_id: some_id
  step_mode: 0  # 0=up, 1=down.
  step_size: 25
  # transition_time:  # In multiples of 100ms. So 10 means 1 second.

# Stop a previous move command.
matter.level_control.stop_with_on_off: some_id
```

# Current Limitations

- Only one device type is supported per endpoint.
- Matter-over-Ethernet has not been verified.
- BLE commissioning is currently broken and if it wasn't, it cannot be combined with the `api` component because of limitations in the ESPHome `network` component.

# See Also

- [esp-matter](https://github.com/espressif/esp-matter)
- [connectedhomeip (espressif's fork)](https://github.com/espressif/connectedhomeip)
- [Matter specification (CSA)](https://csa-iot.org/developer-resource/specifications-download-request/)
