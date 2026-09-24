There are four different lights in Matter; `on_off_light`, `dimmable_light`, `color_temperature_light` and `extended_colour_light`. These are fully supported by esphome-matter.

The `on_off_light` is the simplest light device type. This light only has the OnOff cluster and as the name suggests, only support the "on" and "off" states.

The `dimmable_light` adds the LevelControl cluster on top to support dimming.

The `color_temperature_light` adds the ColorControl cluster to support color temperature.

The `extended_colour_light` is for RGB lights. This device type adds additional attributes and commands to the ColorControl cluster to support the full colour spectrum.

### Pre-defined behaviour

All four lights support the `light_id` config option. This maps a light to a Matter endpoint and handles the default behaviour for a Matter light. This is usually what you want.

```yaml
matter:
  endpoints:
    1:
      extended_colour_light:
        light_id: some_light
        #  It can be useful to set a higher minimum, for example when a low brightness
        #  turns off the light completely. The native Matter level range is 1-254, but
        #  percentages are also valid for the min_level and max_level options.
        # min_level: 1
        # max_level: 254

lights:
  - id: some_light
```

State is synchronized both ways between the ESPHome light entity and Matter. So if you set the brightness via Home Assistant, the Matter brightness attribute will be updated accordingly. The other way around is also true.

##### Power-on behaviour

Matter automatically handles power-on behaviour for lights. The value of the `StartUpOnOff` attribute on the OnOff cluster determines the power-on behaviour. The default is "null" which means the previous state will be restored, but "on", "off" and "toggle" are also possible values.

Besides the `StartUpOnOff` attribute, there is also the `StartUpCurrentLevel` attribute on the `LevelControl` cluster and the `StartUpColorTemperatureMireds` attribute on the `ColorControl` cluster. By default, these are null, which means the previous state will be restored. Currently, Home Assistant has a bug where these values can't be set back to null once set to a numerical value. So if you have set these attributes and want to restore the defaults, you'll have to find another way, possibly by sending raw Matter commands via your Matter controller.

Since Matter now manages the restore behaviour, the `restore_mode` option of an esphome light should not be used anymore.

### Custom behaviour

Alternatively, the behaviour of the light can be defined fully using esphome actions and triggers. The [extended-color-light](../packages/extended-color-light.yaml) package contains a re-implementation of all the pre-defined actions.

### F.A.Q.

Q: Even though the startup behaviour is set to "on" or "previous state", the light doesn't turn on after a restart.
A: Check the StartUpCurrentLevel attribute on the LevelControl cluster. Home Assistant appears to set this to 0 sometimes. This results in a list that is "on" after a restart but with a brightness of zero.

Q: Startup behaviour is set "previous state" but the colour of the light isn't remembered.
A: The StartUpColorTemperatureMireds attribute on the ColorControl cluster might be set to a non-null value. This value must be set to null for colours to be remembered.
