
# Sensors

```yaml
sensor:
  - platform: internal_temperature
    name: "Internal Temperature"
    id: internal_temperature
  
matter:
  endpoints:
    - temperature_sensor:
        sensor_id: internal_temperature
```

# Switches

A matter switch needs a binary_sensor as input. For example;

```yaml
binary_sensor:
  - platform: gpio
    pin: ...
    id: button_up
  - platform: gpio
    pin: ...
    id: button_down
  
matter:
  endpoints:
    - dimmer_switch:
        up_id: button_up
        down_id: button_down
```

### Binding
Switches defined by the matter component automatically get the binding cluster (id 30).
