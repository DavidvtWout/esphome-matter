Almost all device types can be created in esphome-matter. But some require extra configuration to be created correctly. However, creating a device type only allows other Matter devices to interact with these device types. It doesn't automatically mean that ESPHome can do anything useful with the clusters the device type creates yet.

Here is a list of all device types that are currently known to work and what functionality is supported.
For a generated configuration overview of every supported device type and its optional features, see [device_types.md](generated/device_types.md).

# Lights

The Matter light device types are [`on_off_light`](generated/device_types.md#on_off_light), [`dimmable_light`](generated/device_types.md#dimmable_light), [`color_temperature_light`](generated/device_types.md#color_temperature_light), and [`extended_color_light`](generated/device_types.md#extended_color_light). Each adds more functionality to the previous device type.

All of the light device types can be created, but currently only the on/off feature is working.

```yaml
matter:
  endpoints:
    1:
      on_off_light:
        light_id: light_id
    2:
      dimmable_light:
        light_id: light_id
    3:
      color_temperature_light:
        light_id: light_id
    4:
      extended_color_light:
        light_id: light_id
        # Unlike the other lights, the extended_color_light supports additional features;
        with_features:
          - hue_and_saturation # Supports color specification via hue/saturation.
          - enhanced_hue # Enhanced hue is supported.
          - color_loop # Color loop is supported.
```

# Switches

The Matter switch device types are [`on_off_light_switch`](generated/device_types.md#on_off_light_switch), [`dimmer_switch`](generated/device_types.md#dimmer_switch) and [`color_dimmer_switch`](generated/device_types.md#color_dimmer_switch). Instead of mapping an esphome entity to the switch device type, esphome actions are mapped to the endpoint on which the switch is created.

```yaml
matter:
  endpoints:
    1:
      on_off_light_switch:
    2:
      id: dimmer_endpoint
      dimmer_switch:
    3:
      color_dimmer_switch:

switch:
  - name: "Up Button"
    on_click:
      matter.send_command: dimmer_endpoint.on_off.on
    on_press:
      matter.send_command:
        path: dimmer_endpoint.level_control.move_with_on_off
        arguments:
          move_mode: up
          rate: 20%/s
    on_release:
      matter.send_command: dimmer_endpoint.level_control.stop_with_on_off
```

For a complete overview of supported actions, see the documentation on [actions](actions.md).

# Simple sensor device types

The "simple" sensor device types are [`temperature_sensor`](generated/device_types.md#temperature_sensor), [`humidity_sensor`](generated/device_types.md#humidity_sensor), [`light_sensor`](generated/device_types.md#light_sensor), [`pressure_sensor`](generated/device_types.md#pressure_sensor), and [`flow_sensor`](generated/device_types.md#flow_sensor). These all have a similar structure where they expose a measurement cluster with a `MeasuredValue` attribute. These clusters also have the `MinMeasureValue`, `MaxMeasuredValue` and optional `Tolerance` attributes but these aren't supported yet.

```yaml
matter:
  endpoints:
    1:
      temperature_sensor:
        temperature: sensor_id
    2:
      humidity_sensor:
        relative_humidity: sensor_id
    3:
      # The light_sensor also LightSensorType attribute, but setting this attribute isn't supported yet.
      light_sensor:
        illuminance: sensor_id
    4:
      # The pressure_sensor has the `Extended` feature that enables some more attributes, but this isn't supported yet.
      pressure_sensor:
        pressure: sensor_id
    5:
      flow_sensor:
        flow: sensor_id
```

# Binary sensors

There are several binary state sensors. These are [`contact_sensor`](generated/device_types.md#contact_sensor), [`occupancy_sensor`](generated/device_types.md#occupancy_sensor), [`rain_sensor`](generated/device_types.md#rain_sensor), and [`soil_sensor`](generated/device_types.md#soil_sensor). Unlike the simple sensors, these sensors all expose the same boolean_state cluster.

```yaml
matter:
  endpoints:
    1:
      contact_sensor:
        boolean_state: binary_sensor_id
    2:
      rain_sensor:
        boolean_state: binary_sensor_id
        with_features:
          - visual # Supports visual alarms
          - audible # Supports audible alarms
          - alarm_suppress # Supports ability to suppress or acknowledge alarms
          - sensitivity_level # Supports ability to set sensor sensitivity
          - fault_events # Supports reporting fault events
    3:
      soil_sensor:
        boolean_state: binary_sensor_id
        # The soil_sensor has optional support for temperature measurements;
        # temperature: temperature_id
    4:
      occupancy_sensor:
        boolean_state: binary_sensor_id
```

# [air_quality_sensor](generated/device_types.md#air_quality_sensor)

The `Air Quality Sensor` supports many concentration measurements as well as temperature and humidity. Each measurement gets its own cluster. These clusters are only created when a sensor_id is mapped to that measurement cluster.

```yaml
matter:
  endpoints:
    1:
      air_quality_sensor:
        temperature: temperature_id
        relative_humidity: humidity_id
        carbon_monoxide: co_id
        carbon_dioxide: co2_id
        nitrogen_dioxide: no2_id
        ozone: ozone_id
        pm_1: pm_1_id
        pm_2_5: pm_2_5_id
        pm_10: pm_10_id
        formaldehyde: formaldehyde_id
        total_voc: total_voc_id
        radon: radon_id
```

# [electrical_sensor](generated/device_types.md#electrical_sensor)

This device type exposes clusters and attributes for power and energy measurements. However, this device type currently can't successfully be created in esphome-matter yet.

# Untested / unsupported

The following device types are untested. Many of them can still successfully be created. Interactions with these device types can be done with the [set_attribute](actions.md#set_attribute) action and [on_attribute](actions.md#on_attribute) trigger.

- [`door_lock`](generated/device_types.md#door_lock)
- [`aggregator`](generated/device_types.md#aggregator)
- [`generic_switch`](generated/device_types.md#generic_switch)
- [`power_source`](generated/device_types.md#power_source)
- [`ota_requestor`](generated/device_types.md#ota_requestor)
- [`bridged_node`](generated/device_types.md#bridged_node)
- [`ota_provider`](generated/device_types.md#ota_provider)
- [`root_node`](generated/device_types.md#root_node)
- [`solar_power`](generated/device_types.md#solar_power)
- [`battery_storage`](generated/device_types.md#battery_storage)
- [`secondary_network_interface`](generated/device_types.md#secondary_network_interface)
- [`mode_select`](generated/device_types.md#mode_select)
- [`fan`](generated/device_types.md#fan)
- [`air_purifier`](generated/device_types.md#air_purifier)
- [`water_freeze_detector`](generated/device_types.md#water_freeze_detector)
- [`water_valve`](generated/device_types.md#water_valve)
- [`water_leak_detector`](generated/device_types.md#water_leak_detector)
- [`refrigerator`](generated/device_types.md#refrigerator)
- [`temperature_controlled_cabinet`](generated/device_types.md#temperature_controlled_cabinet)
- [`room_air_conditioner`](generated/device_types.md#room_air_conditioner)
- [`laundry_washer`](generated/device_types.md#laundry_washer)
- [`robotic_vacuum_cleaner`](generated/device_types.md#robotic_vacuum_cleaner)
- [`dishwasher`](generated/device_types.md#dishwasher)
- [`smoke_co_alarm`](generated/device_types.md#smoke_co_alarm)
- [`cook_surface`](generated/device_types.md#cook_surface)
- [`cooktop`](generated/device_types.md#cooktop)
- [`microwave_oven`](generated/device_types.md#microwave_oven)
- [`extractor_hood`](generated/device_types.md#extractor_hood)
- [`oven`](generated/device_types.md#oven)
- [`laundry_dryer`](generated/device_types.md#laundry_dryer)
- [`thread_border_router`](generated/device_types.md#thread_border_router)
- [`on_off_plug_in_unit`](generated/device_types.md#on_off_plug_in_unit)
- [`dimmable_plug_in_unit`](generated/device_types.md#dimmable_plug_in_unit)
- [`mounted_on_off_control`](generated/device_types.md#mounted_on_off_control)
- [`mounted_dimmable_load_control`](generated/device_types.md#mounted_dimmable_load_control)
- [`audio_doorbell`](generated/device_types.md#audio_doorbell)
- [`camera`](generated/device_types.md#camera)
- [`video_doorbell`](generated/device_types.md#video_doorbell)
- [`chime`](generated/device_types.md#chime)
- [`doorbell`](generated/device_types.md#doorbell)
- [`window_covering`](generated/device_types.md#window_covering)
- [`closure`](generated/device_types.md#closure)
- [`closure_panel`](generated/device_types.md#closure_panel)
- [`closure_controller`](generated/device_types.md#closure_controller)
- [`thermostat`](generated/device_types.md#thermostat)
- [`pump`](generated/device_types.md#pump)
- [`pump_controller`](generated/device_types.md#pump_controller)
- [`heat_pump`](generated/device_types.md#heat_pump)
- [`thermostat_controller`](generated/device_types.md#thermostat_controller)
- [`evse`](generated/device_types.md#evse)
- [`device_energy_management`](generated/device_types.md#device_energy_management)
- [`water_heater`](generated/device_types.md#water_heater)
- [`electrical_utility_meter`](generated/device_types.md#electrical_utility_meter)
- [`electrical_energy_tariff`](generated/device_types.md#electrical_energy_tariff)
- [`electrical_meter`](generated/device_types.md#electrical_meter)
- [`control_bridge`](generated/device_types.md#control_bridge)
