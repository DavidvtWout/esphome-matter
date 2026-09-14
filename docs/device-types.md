Almost all device types can be created in esphome-matter. But some require extra configuration to be created correctly. However, creating a device type only allows other Matter devices to interact with these device types. It doesn't automatically mean that ESPHome can do anything useful with the clusters the device type creates yet.

Here is a list of all device types that are currently known to work and what functionality is supported.

# Lights

The Matter light device types are `on_off_light`, `dimmable_light`, `color_temperature_light`, and `extended_color_light`. Each adds more functionality to the previous device type.

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
```

# Switches

The Matter switch device types are `on_off_light_switch`, `dimmer_switch` and `color_dimmer_switch`. Instead of mapping an esphome entity to the switch device type, esphome actions are mapped to the endpoint on which the switch is created.

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
      matter.on_off.on: dimmer_endpoint
    on_press:
      matter.level_control.move_with_on_off:
        endpoint_id: dimmer_endpoint
        move_mode: up
        rate: 20%/s
    on_release:
      matter.level_control.stop_with_on_off: dimmer_endpoint
```

For a complete overview of supported actions, see the documentation on [actions](actions.md).

# Simple sensor device types

The "simple" sensor device types are `Temperature Sensor`, `Humidity Sensor`, `Light Sensor`, `Pressure Sensor`, `Flow Sensor`. These all have a similar structure where they expose a measurement cluster with a `MeasuredValue` attribute. These clusters also have the `MinMeasureValue`, `MaxMeasuredValue` and optional `Tolerance` attributes but these aren't supported yet.

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

There are several binary state sensors. These are `contact_sensor`, `occupancy_sensor`, `rain_sensor`, `soil_sensor`. Unlike the simple sensors, these sensors all expose the same boolean_state cluster.

```yaml
matter:
  endpoints:
    1:
      contact_sensor:
        boolean_state: binary_sensor_id
    2:
      occupancy_sensor:
        boolean_state: binary_sensor_id
    3:
      soil_sensor:
        boolean_state: binary_sensor_id
    4:
      occupancy_sensor:
        boolean_state: binary_sensor_id
```

# air_quality_sensor

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

# electrical_sensor

This device type exposes clusters and attributes for power and energy measurements. However, this device type currently can't successfully be created in esphome-matter yet.

# Untested / unsupported

The following device types are untested. Many of them can still successfully be created, but besides sensor attributes, little interaction can be done with these.

- door_lock
- aggregator
- generic_switch
- power_source
- ota_requestor
- bridged_node
- ota_provider
- root_node
- solar_power
- battery_storage
- secondary_network_interface
- mode_select
- fan
- air_purifier
- water_freeze_detector
- water_valve
- water_leak_detector
- refrigerator
- temperature_controlled_cabinet
- room_air_conditioner
- laundry_washer
- robotic_vacuum_cleaner
- dishwasher
- smoke_co_alarm
- cook_surface
- cooktop
- microwave_oven
- extractor_hood
- oven
- laundry_dryer
- thread_border_router
- on_off_plug_in_unit
- dimmable_plug_in_unit
- mounted_on_off_control
- mounted_dimmable_load_control
- audio_doorbell
- camera
- video_doorbell
- chime
- doorbell
- window_covering
- closure
- closure_panel
- closure_controller
- thermostat
- pump
- pump_controller
- heat_pump
- thermostat_controller
- evse
- device_energy_management
- water_heater
- electrical_utility_meter
- electrical_energy_tariff
- electrical_meter
- control_bridge
