Matter devices are controlled through clusters. A cluster groups related behavior, and commands are the operations sent to that cluster. For example, the OnOff cluster has commands such as `on`, `off`, and `toggle`, while the LevelControl cluster has commands for dimming.

Before a command can be sent, a client device (for example a button) must be [bound](./binding.md) to a server device (for example a light).

Commands can use a complete Matter command path:

```yaml
matter.send_command:
  path: some_endpoint.on_off.toggle
```

Or the endpoint, cluster, and command can be written separately:

```yaml
matter.send_command:
  endpoint: some_endpoint
  cluster: on_off
  command: toggle
```

First define a device type that supports binding and give it an `id`:

```yaml
matter:
  endpoints:
    1:
      id: dimmer_endpoint
      # A dimmer_switch doesn't need specific configuration to be created so you can keep it "bare".
      dimmer_switch:
```

After the endpoint has been bound in your Matter controller, automations can call the command actions that are listed below using that endpoint id:

```yaml
binary_sensor:
  - name: "Some button"
    on_click:
      matter.send_command: dimmer_endpoint.on_off.toggle # 1.on_off.toggle is also accepted
```

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
    transition_time: 1.5s

matter.send_command:
  path: some_endpoint.level_control.step
  arguments:
    step_mode: 1
    step_size: 127
    transition_time: 15
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

Identify commands make a device identify itself. This is mostly useful while commissioning or debugging, so you can confirm which physical device is receiving commands.

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
    # effect_variant: 0 - Depends on the specific device what options are supported.
```

### OnOff cluster

OnOff commands are used for simple binary devices such as lights, plugs and relays.

```yaml
# Turn off, turn on, or toggle a bound device. These have no arguments so the shorthand notation is possible.
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

# This command allows the recall of the settings when the device was turned off.
matter.send_command: some_endpoint.on_off.on_with_recall_global_scene

# Intended for motion sensors temporarily turning on a light.
# Official description: This command allows devices to be turned on for a specific duration with a
#  guarded off duration so that SHOULD the device be subsequently turned off, further OnWithTimedOff
#  commands, received during this time, are prevented from turning the devices back on.
matter.send_command:
  path: some_endpoint.on_off.on_with_timed_off
  arguments:
    on_time: # s
    # on_off_control: []  # Bitmap option: accept_only_when_on
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

### ColorControl cluster

ColorControl commands are used both for colour temperature control and RGB colour control.

##### Temperature

Colour temperature is measured in mireds, which is nice because ESPHome also uses mireds.

```yaml
# This command will move the device to the requested color temperate using a transition.
matter.send_command:
  path: some_endpoint.color_control.move_to_color_temperature
  arguments:
    color_temperature_mireds:
    # transition_time: 0s

# This command allows the color temperature of the light to be moved at a specified rate.
matter.send_command:
  path: some_endpoint.color_control.move_color_temperature
  arguments:
    move_mode: # enum: stop, up, down
    rate:
    # color_temperature_minimum_mireds: 0
    # color_temperature_maximum_mireds: 0

# This command allows the color temperature of the light to be stepped with a specified step size.
matter.send_command:
  path: some_endpoint.color_control.step_color_temperature
  arguments:
    step_mode: # enum: up, down
    step_size:
    # transition_time: 0s
    # color_temperature_minimum_mireds: 0
    # color_temperature_maximum_mireds: 0
```

##### Hue / Saturation

There are also "enhanced" commands. I'm not sure what the difference it with the normal command but you can find them at the [ColorControl](commands-full.md#colorcontrol) section of commands-full.md.

```yaml
# This command will move the device to the requested hue using a transition.
matter.send_command:
  path: some_endpoint.color_control.move_to_hue
  arguments:
    hue:
    direction: # enum: shortest, longest, up, down
    # transition_time: 0s

# This command will change the hue of the device with a requested rate.
matter.send_command:
  path: some_endpoint.color_control.move_hue
  arguments:
    move_mode: # enum: stop, up, down
    rate:

# This command will change the hue of the device using a step and transition.
matter.send_command:
  path: some_endpoint.color_control.step_hue
  arguments:
    step_mode: # enum: up, down
    step_size:
    # transition_time: 0s

# This command will move the device to the requested saturation using a transition.
matter.send_command:
  path: some_endpoint.color_control.move_to_saturation
  arguments:
    saturation:
    # transition_time: 0s

# This command will change the saturation of the device with a requested rate.
matter.send_command:
  path: some_endpoint.color_control.move_saturation
  arguments:
    move_mode: # enum: stop, up, down
    rate:

# This command will change the saturation of the device using a step and transition.
matter.send_command:
  path: some_endpoint.color_control.step_saturation
  arguments:
    step_mode: # enum: up, down
    step_size:
    # transition_time: 0s

# This command will move the device to the requested hue and saturation using a transition.
matter.send_command:
  path: some_endpoint.color_control.move_to_hue_and_saturation
  arguments:
    hue:
    saturation:
    # transition_time: 0s

# This command is provided to allow MoveTo and Step commands to be stopped.
matter.send_command: some_endpoint.color_control.stop_move_step
```

##### Colour

```yaml
# This command will move the device to the requested color using a transition.
matter.send_command:
  path: some_endpoint.color_control.move_to_color
  arguments:
    color_x:
    color_y:
    # transition_time: 0s

# This command will change the color of the device with a requested rate.
matter.send_command:
  path: some_endpoint.color_control.move_color
  arguments:
    rate_x:
    rate_y:

# This command will change the color of the device using a step and transition.
matter.send_command:
  path: some_endpoint.color_control.step_color
  arguments:
    step_x:
    step_y:
    # transition_time: 0s

# This command allows a color loop to be activated such that the color light cycles through its range of hues.
matter.send_command:
  path: some_endpoint.color_control.color_loop_set
  arguments:
    # update_flags: [] # bitmap: update_action, update_direction, update_time, update_start_hue
    action: # enum: deactivate, activate_from_color_loop_start_enhanced_hue, activate_from_enhanced_current_hue
    direction: # enum: decrement, increment
    time:
    start_hue:

# This command is provided to allow MoveTo and Step commands to be stopped.
matter.send_command: some_endpoint.color_control.stop_move_step
```
