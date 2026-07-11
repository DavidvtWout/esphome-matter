
A matter switch needs a binary_sensor as input. For example;

```yaml
binary_sensor:
  - platform: gpio
    pin: ...
    id: up_button
  - platform: gpio
    pin: ...
    id: down_button
  
matter:
  switches:
    - id: up_button
      endpoint_id: 1
      device_type: momentary_long_press
    - id: down_button
      endpoint_id: 2
      device_type: momentary_long_press
```

Supported device types:
- latched: toggle/rocker switch with stable positions
- momentary: push-button that springs back.
- momentary_release:
- momentary_long_press:
- momentary_multi_press:
- momentary_full:

### Binding
Switches defined by the matter component automatically get the binding cluster (id 30).
