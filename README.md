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
  devices:
    - device_type: dimmer_switch
      # IDs must match with IDs defined under binary_sensors.
      up_id: button_up
      down_id: button_down
      # Not strictly needed to specify the endpoint_id, but if unspecified these will be auto-generated. If you later
      # add another device that may change the endpoint_id which breaks binding and automations that use the endpoint_id.
      endpoint_id: 1

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
