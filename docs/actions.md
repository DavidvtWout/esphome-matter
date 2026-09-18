Matter devices are controlled through clusters. A cluster groups related behavior, and commands are the operations sent to that cluster. For example, the OnOff cluster has commands such as `on`, `off`, and `toggle`, while the LevelControl cluster has commands for dimming.

In esphome-matter, these actions work like a Matter switch or remote control. You first bind one of the ESPHome Matter endpoints to another Matter device, such as a light, in your Matter controller. After that, an ESPHome automation can call `matter.send_command`, and the command is sent to the device that was bound to that endpoint.

Bound actions require the endpoint to include the Binding cluster. Device types such as `on_off_light_switch` and `dimmer_switch` include it as required by Matter.

Commands can use a complete Matter command path:

```yaml
matter.send_command:
  path: switch_endpoint.level_control.move
  arguments:
    move_mode: up
    rate: 20%/s
```

Or the endpoint, cluster, and command can be written separately:

```yaml
matter.send_command:
  endpoint: switch_endpoint
  cluster: level_control
  command: move
  arguments:
    move_mode: up
    rate: 20%/s
```

The older `matter.<cluster>.<command>` actions remain available for compatibility but are deprecated.

First define a device type that supports binding and give it an `id`:

```yaml
matter:
  endpoints:
    1:
      id: dimmer_endpoint
      dimmer_switch:

binary_sensor:
  - name: "Some button"
    on_click:
      matter.send_command: dimmer_endpoint.on_off.toggle # 1 is also accepted
```

After the endpoint has been bound in your Matter controller, automations can call the command actions below using that endpoint id.

Command fields accept raw Matter integer values. Common LevelControl and timing fields also accept explicit units such as percentages, `%/s`, and seconds. Required fields are shown uncommented. Optional fields are commented out and show the default value used when you omit them.

### Units

Internally command fields are integers and Matter defines the meaning of each field. For example, the transition time for move and step commands is measured in multiples of 100ms. So a value of 15 means 1.5s. All command fields support raw integer values, but it's recommended to specify the unit. This way, the unit is automatically converted to the correct Matter value.

Light levels are divided into 254 steps and a percentage value is rounded to the nearest step. For rates, the `%/s` unit can be used.

Some fields have a distinct set of accepted values. For example the `step_mode` of the `level_control.step` can be 0 or 1 meaning `up` or `down`. In the commands below, the supported string values are shown in the comment behind the field name. These strings are automatically converted to the correct integer value.

So for example the following two commands are equivalent:

```yaml
matter.send_command:
  path: some_endpoint.level_control.step
  arguments:
    step_mode: down
    step_size: 50%
    transition_time: 2s

matter.send_command:
  endpoint: 1  # Assuming some_endpoint is attached to endpoint 1.
  cluster: level_control
  command: step
  arguments:
    step_mode: 1
    step_size: 127
    transition_time: 20
```

### enums

Some command arguments are "enums". These are actually integers but with names mapped to specific values. One such example is the `move_mode` argument in some of the `level_control` commands. This is an integer with a value of either 0 or 1 where 0 means "up" and 1 means "down". In the commands below, the supported values are mentioned in the comment behind the argument. esphome-matter supports either the name in snake_case format or the integer value.

### bitmasks

Arguments can also be of the "bitmask" type. Just like the enum, internally this is just an integer.

Take for example the `days_mask`. Each day is represented by a bit. `sunday:1`, `monday:2`, `tuesday:4`, `wednesday:8` etc... The value is the sum of all active options.

```yaml
# A single mask can be applied directly;
days_mask: monday
# The following command args are all equivalent;
days_mask: ["saturday", "sunday"]
days_mask:
  - saturday
  - sunday
days_mask: 65
```

# Cluster commands

### Identify cluster

Identify commands make a bound device identify itself. This is mostly useful while commissioning or debugging, so you can confirm which physical device is receiving commands.

```yaml
# Ask the device to identify itself for a number of seconds.
matter.send_command:
  path: some_endpoint.identify.identify
  arguments:
    identify_time: # s - Use 0s to stop identifying

# Trigger a specific identify effect, if the bound device supports it.
matter.send_command:
  path: some_endpoint.identify.trigger_effect
  arguments:
    effect_identifier: # Either blink, breathe, okay, channel_effect, finish_effect or stop_effect
    # effect_variant: 0
```

### OnOff cluster

OnOff commands are used for simple binary devices such as lights, plugs and relays.

```yaml
# Turn off, turn on, or toggle a bound device.
matter.send_command: some_endpoint.on_off.on
matter.send_command: some_endpoint.on_off.on
matter.send_command: some_endpoint.on_off.toggle

# Turn off with a visual effect, if the bound device supports it.
# Common effect_identifier values are 0=delayed all off and 1=dying light.
matter.send_command:
  path: some_endpoint.on_off.off_with_effect
  arguments:
    effect_identifier: # Either delayed_all_off or dying_light
    # effect_variant: 0

# Turn on and recall the device's global scene, if the device supports scenes.
matter.send_command: some_endpoint.on_off.on_with_recall_global_scene

# Intended for motion sensors temporarily turning on a light.
matter.send_command:
  path: some_endpoint.on_off.on_with_timed_off
  arguments:
    on_time: # s
    # on_off_control: 0  # No idea what this does. You'll have to figure that out yourself.
    # off_wait_time: 0s  # Time before accepting another on_with_timed_off command.
```

### LevelControl cluster

LevelControl commands are used for dimming. Levels can be percentages or raw Matter brightness levels, normally `0` to `254`.

The commands with `_with_on_off` also affect the OnOff state, which is usually what you want. For example, moving to a non-zero level may turn the light on, and moving to level `0` may turn it off. The commands without `_with_on_off` only change the level and do not directly change the OnOff state.

```yaml
# Move directly to a brightness level.
matter.send_command:
  path: some_endpoint.level_control.move_to_level
  arguments:
    level: # %
    # transition_time: 0s

# Move continuously up or down until a stop command is sent or the device
# reaches its minimum/maximum level.
matter.send_command:
  path: some_endpoint.level_control.move
  arguments:
    move_mode: # Either up or down.
    rate: # %/s

# Step once by a fixed amount.
matter.send_command:
  path: some_endpoint.level_control.step
  arguments:
    step_mode: # Either up or down
    step_size: # %
    # transition_time: 0s

# Stop a previous move command.
matter.send_command: some_endpoint.level_control.stop

# Move directly to a brightness level and allow the device to update OnOff state.
matter.send_command:
  path: some_endpoint.level_control.move_to_level_with_on_off
  arguments:
    level: # %
    # transition_time: 0s

# Move continuously up or down and allow the device to update OnOff state.
matter.send_command:
  path: some_endpoint.level_control.move_with_on_off
  arguments:
    move_mode: # Either up or down
    rate: # %/s

# Step once by a fixed amount and allow the device to update OnOff state.
matter.send_command:
  path: some_endpoint.level_control.step_with_on_off
  arguments:
    step_mode: # Either up or down
    step_size: # %
    # transition_time: 0s

# Stop a previous move-with-on-off command.
matter.send_command: some_endpoint.level_control.stop_with_on_off
```
