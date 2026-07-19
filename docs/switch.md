
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
