# esphome-matter
ESPHome external component for matter support.

This is currently a proof-of-concept and not really usable yet.

Do you like the idea of matter support in esphome? Give this project a star! Then I'll know people are interested.

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
        # IDs must match with IDs defined under binary_sensors.
        up_id: button_up
        down_id: button_down

# The two buttons are configured to be triggered when the GPIO pin is pulled down to GND.
binary_sensor:
  - name: "Button up"
    id: button_up
    platform: gpio
    pin:
      number: GPIO0
      mode:
        pullup: true
        input: true
      inverted: true
  - name: "Button down"
    id: button_down
    platform: gpio
    pin:
      number: GPIO1
      mode:
        pullup: true
        input: true
      inverted: true
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
