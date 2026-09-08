Almost all device type can be created in esphome-matter. But some require extra configuration to be created correctly. However, creating a device type only allows other Matter devices to interact with these device type. It doesn't automatically mean that ESPHome can do anything useful with the clusters the device type creates yet.

Here is a list of all device types that are currently known to work and what functionality is supported.

# Simple sensor device types

### Temperature Sensor

```
RelativeHumidityMeasurement
  attributes
  - MeasuredValue
  - MinMeasuredValue
  - MaxMeasuredValue
  # Optional:
  - Tolerance
```

### Humidity Sensor

### Light Sensor

```
IlluminanceMeasurement
  attributes:
  - MeasuredValue
  - MinMeasuredValue
  - MaxMeasuredValue
  # Optional:
  - Tolerance
  - LightSensorType: LightSensorTypeEnum (Photodiode or CMOS)
```

### Pressure Sensor

```
PressureMeasurement
  features:
  - Extended
  attributes:
  - MeasuredValue
  - MinMeasuredValue
  - MaxMeasuredValue
  # Optional:
  - Tolerance
  - ScaledValue
  -
```

### Flow Sensor

### Contact Sensor

```
BooleanState
  features
  - ChangeEvent
  attibutes
  - StateValue
```

# Other sensor device types

###

# Tested

- root_node
- on_off_light
- dimmable_light
- on_off_light_switch
- dimmer_switch
- color_dimmer_switch
- air_quality_sensor
- temperature_sensor
- pressure_sensor
- flow_sensor
- humidity_sensor

# Most interesting for ESPHome

These are likely to provide the most value once their clusters and ESPHome entity
mappings are implemented. They remain in the untested lists below until verified.

# Untested

The following device types can be created, but have not yet been verified with a
Matter controller or physical device. They are grouped by their primary purpose.

## Lighting, switches, and outlets

- generic_switch
- mode_select
- color_temperature_light
- extended_color_light
- on_off_plug_in_unit
- dimmable_plug_in_unit
- mounted_on_off_control
- mounted_dimmable_load_control

## Sensors

- contact_sensor
- light_sensor
- occupancy_sensor
- ambient_context_sensor
- proximity_ranger
- water_freeze_detector
- water_leak_detector
- rain_sensor
- soil_sensor
- smoke_co_alarm
- on_off_sensor

## Climate, air, and water control

- fan
- air_purifier
- room_air_conditioner
- humidifier_dehumidifier
- thermostat
- thermostat_controller
- heat_pump
- pump
- pump_controller
- water_heater
- water_valve

## Energy and electrical systems

- power_source
- solar_power
- battery_storage
- evse
- device_energy_management
- electrical_sensor
- electrical_utility_meter
- meter_reference_point
- electrical_meter
- electrical_circuit_breaker
- electrical_distribution_enclosure

## Locks, windows, and closures

- door_lock
- door_lock_controller
- window_covering
- window_covering_controller
- closure
- closure_panel
- closure_controller

## Appliances

- refrigerator
- laundry_washer
- laundry_dryer
- robotic_vacuum_cleaner
- dishwasher
- cook_surface
- cooktop
- extractor_hood
- oven

## Media and entertainment

- speaker
- casting_video_player
- casting_video_client
- content_app
- basic_video_player
- video_remote_control

## Cameras, doorbells, and intercoms

- intercom
- audio_doorbell
- camera
- video_doorbell
- floodlight_camera
- snapshot_camera
- chime
- camera_controller
- doorbell

## Network and Matter infrastructure

- aggregator
- bridged_node
- ota_requestor
- ota_provider
- network_infrastructure_manager
- secondary_network_interface
- thread_border_router

# No intention to support

These infrastructure roles do not currently fit the intended use of an ESPHome
Matter endpoint:

- joint_fabric_administrator
- microwave_oven
- control_bridge

# Incompatible with ESPHome

- orphan_clusters

# Bullshit device types that shouldn't exist

- electrical_energy_tariff (How is a tariff a device type?!?)
- temperature_controlled_cabinet
- all_clusters_app_server_example
