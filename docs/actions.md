There are multiple ways to interact with Matter endpoints/clusters/attributes. One of these is via commands.

Some device types implement the binding cluster. In esphome-matter, these are the `on_off_light_switch`, `dimmer_switch` and `color_dimmer_switch` (The `generic_switch` does NOT implement binding!).

Endpoints that "contain" one of these device types support sending commands "into" them.

```yaml
matter:
  endpoints:
    - dimmer_switch:
      id: dimmer_endpoint

```

### OnOff cluster

```yaml
# turn on/off or toggle a light
matter.on_off.off: some_id
matter.on_off.on: some_id
matter.on_off.toggle: some_id
# Intended for motion sensors temporarily turning on a light.
matter.on_off.on_with_timed_off:
  endpoint_id: some_id
  on_time: # How long to turn on the light in multiples of 100ms. So 150 means 15 seconds.
  # on_off_control:
  # on_wait_time: 
```

### LevelControl Cluster

```yaml
# 
matter.level_control.move_to_level:
  endpoint_id: some_id
  
```
