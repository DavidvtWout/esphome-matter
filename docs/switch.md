
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
  devices:
    - device_type: dimmer_switch
      up_id: button_up
      down_id: button_down
      endpoint_id: 1
    - device_type: on_off_switch
      id: button_on_off
      endpoint_id: 2
```

### Binding
Switches defined by the matter component automatically get the binding cluster (id 30).
