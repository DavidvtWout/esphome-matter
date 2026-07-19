# esphome-matter
ESPHome external component for matter support.

It's still in early-development. Currently only the `on_off_switch`, `dimmer_switch`, `temperature_sensor`,
`on_off_light` and `dimmable_light` matter endpoints are supported.

The main limitation is that it currently isn't yet compatible with the `network` component. And since the
`api` components requires `network`, there is no way to combine the api with matter. Incompatibility with `network`
also means no `wifi`, `ethernet` or `openthread` can be configured. The thread TLV is passed to matter during commissioning
and this is currently the only way to set up matter-over-thread. I think it will be possible to support matter-over-wifi and 
matter-over-ethernet soon.

I completely disabled wifi support to make it easier to implement matter-over-thread. This will also be fixed in the future.

# Compilation

esphome-matter requires the esp-idf framework. The arduino framework won't work. Since esphome 2026.1.0 this is the
default anyway, but if you're still on an earlier version you need to specify the framework;

```yaml
esp32:
  framework:
    type: esp-idf
```

# Example config

The ESPHome `network` components isn't really build for IPv6 and messes things up a bit... Since this component is
required for the `api` component, the api also can't be enabled for now. With this example config matter will start
in BLE commissioning mode. Only matter-over-thread is supported for now. Once commissioned, you can bind the 
button to a matter light.

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

> [!WARNING]
> **Endpoint IDs must stay stable.** Matter endpoint IDs are assigned by list order:
> the first entry under `endpoints:` becomes endpoint 1, the second endpoint 2, and so on.
> Other devices and controllers reference these IDs in their bindings and ACLs, so once the
> device is commissioned, treat the list as append-only:
>
> - **Never reorder or remove entries.** Removing a middle entry shifts every endpoint after
>   it down by one, breaking their bindings.
> - **Never change the device type of an existing entry.** The endpoint keeps its ID but its
>   clusters change, which invalidates bindings targeting it.
> - **Adding new entries at the end is safe.**
>
> If you must restructure the list, re-commission the device afterwards and recreate its
> bindings (and clean up stale ACL entries on bound devices).
