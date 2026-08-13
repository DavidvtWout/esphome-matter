Matter devices are controlled through clusters. A cluster groups related behavior, and commands are the operations sent to that cluster. For example, the OnOff cluster has commands such as `on`, `off`, and `toggle`, while the LevelControl cluster has commands for dimming.

In esphome-matter, these actions work like a Matter switch or remote control. You first bind one of the ESPHome Matter endpoints to another Matter device, such as a light, in your Matter controller. After that, an ESPHome automation can call actions like `matter.on_off.toggle` or `matter.level_control.move_with_on_off`, and the command is sent to the device that was bound to that endpoint.

Only some device types include the Binding cluster. In esphome-matter these are `on_off_light_switch`, `dimmer_switch`, and `color_dimmer_switch`. The `generic_switch` device type does not support binding, so it cannot send these bound commands.

First define an endpoint that supports binding and give it an `id`:

```yaml
matter:
  endpoints:
    - dimmer_switch:
      id: dimmer_endpoint

binary_sensor:
  - name: "Some button"
    on_click:
      matter.on_off.toggle: dimmer_endpoint
```

After the endpoint has been bound in your Matter controller, automations can call the command actions below using that endpoint id.

Field values use the raw Matter units for now. Units like percentage or seconds will be added later. Required fields are shown uncommented. Optional fields are commented out and show the default value used when you omit them.

### Identify cluster

Identify commands make a bound device identify itself. This is mostly useful while commissioning or debugging, so you can confirm which physical device is receiving commands.

```yaml
# Ask the device to identify itself for a number of seconds.
matter.identify.identify:
  endpoint_id:
  identify_time:  # Seconds. Use 0 to stop identifying.

# Trigger a specific identify effect, if the bound device supports it.
matter.identify.trigger_effect:
  endpoint_id:
  effect_identifier:  # 0=blink, 1=breathe, 2=okay, 0xFE=finish current effect, 0xFF=stop current effect.
  # effect_variant: 
```

### OnOff cluster

OnOff commands are used for simple binary devices such as lights, plugs and relays.

```yaml
# Turn off, turn on, or toggle a bound device.
matter.on_off.off: some_id
matter.on_off.on: some_id
matter.on_off.toggle: some_id

# Turn off with a visual effect, if the bound device supports it.
# Common effect_identifier values are 0=delayed all off and 1=dying light.
matter.on_off.off_with_effect:
  endpoint_id: some_id
  effect_identifier: 0
  # effect_variant: 0

# Turn on and recall the device's global scene, if the device supports scenes.
matter.on_off.on_with_recall_global_scene: some_id

# Intended for motion sensors temporarily turning on a light.
matter.on_off.on_with_timed_off:
  endpoint_id:
  on_time:  # How long to turn on the light in multiples of 100ms. So 150 means 15 seconds.
  # on_off_control: 0  # No idea what this does. You'll have to figure that out yourself.
  # off_wait_time: 0  # Time before accepting another on_with_timed_off command, in multiples of 100ms.
```

### LevelControl cluster

LevelControl commands are used for dimming. Levels are raw Matter brightness levels, normally `0` to `254`.

The commands with `_with_on_off` also affect the OnOff state, which is usually what you want. For example, moving to a non-zero level may turn the light on, and moving to level `0` may turn it off. The commands without `_with_on_off` only change the level and do not directly change the OnOff state.

```yaml
# Move directly to a brightness level.
matter.level_control.move_to_level:
  endpoint_id:
  level:
  # transition_time: 0  # In multiples of 100ms. So 10 means 1 second.

# Move continuously up or down until a stop command is sent or the device
# reaches its minimum/maximum level.
matter.level_control.move:
  endpoint_id:
  move_mode:  # 0=up, 1=down.
  rate:  # Level units per second.

# Step once by a fixed amount.
matter.level_control.step:
  endpoint_id:
  step_mode:  # 0=up, 1=down.
  step_size:
  # transition_time: 0  # In multiples of 100ms. So 10 means 1 second.

# Stop a previous move command.
matter.level_control.stop: some_id

# Move directly to a brightness level and allow the device to update OnOff state.
matter.level_control.move_to_level_with_on_off:
  endpoint_id:
  level:
  # transition_time: 0  # In multiples of 100ms. So 10 means 1 second.

# Move continuously up or down and allow the device to update OnOff state.
matter.level_control.move_with_on_off:
  endpoint_id:
  move_mode:  # 0=up, 1=down.
  rate:  # Level units per second.

# Step once by a fixed amount and allow the device to update OnOff state.
matter.level_control.step_with_on_off:
  endpoint_id:
  step_mode:  # 0=up, 1=down.
  step_size:
  # transition_time: 0  # In multiples of 100ms. So 10 means 1 second.

# Stop a previous move-with-on-off command.
matter.level_control.stop_with_on_off: some_id
```
