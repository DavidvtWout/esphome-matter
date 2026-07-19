
# Lights

```yaml
matter:
  endpoints:
    - on_off_light:
        light_id: user_led

output:
  # Seeed studio XIAO-ESP32-C6
  - platform: gpio
    pin:
      number: GPIO15
      inverted: true
    id: user_led_pin

light:
  - platform: binary
    id: user_led
    name: "User LED"
    output: user_led_pin
```

# Sensors

```yaml
matter:
  endpoints:
    - temperature_sensor:
        sensor_id: internal_temperature

sensor:
  - platform: internal_temperature
    name: "Internal Temperature"
    id: internal_temperature
```

# Switches

esphome-matter supports two types of switches; `on_off_switch` and `dimmer_switch`. The first one allows the
`matter.turn_on` and `matter.turn_off` actions on it. The second one also `matter.dim_up`, `matter.dim_down` and 
`matter.dim_stop`.

```yaml
matter:
  endpoints:
    - dimmer_switch:
      id: dimmer_endpoint

binary_sensor:
  - platform: gpio
    pin: ...
    on_click:
      matter.turn_on:
        id: dimmer_endpoint
    on_press:
      matter.dim_up:
        id: dimmer_endpoint
    on_release:
      matter.dim_stop:
        id: dimmer_endpoint
  - platform: gpio
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
```

### Binding
Switches defined by the matter component automatically get the binding cluster (id 30).
