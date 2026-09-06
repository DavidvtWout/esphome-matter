Each endpoint is defined by its ID which can range from 0 to 65534. An endpoint at id 0 with device type `Root Node` is always created. This device type defines clusters such as `AccessControl`, `BasicInformation`, diagnostic clusters and clusters that are used for commissioning.

Beneath an endpoint are clusters. Clusters are collections of attributes and commands with more or less a single function. For example the `OnOff` cluster defines attributes such as the state, startup behaviour and defines commands such as `on`, `off` and `toggle`.

# Device types

To make cluster management more convenient, Matter defines device types. For example the `Dimmable Light` creates clusters such as `OnOff` and `LevelControll`. Different device types may define the same clusters so if you're not sure, it's best to assign only a single device type to each endpoint.

### Lights

```yaml
# A simple light that can only be turned on and off.
on_off_light:
  light_id:

# Dimmable light.
dimmable_light:
  light_id:
```

### Switches

```yaml
# Defines the OnOff cluster.
on_off_light_switch:

# Defines both the OnOff and LevelControl clusters.
dimmer_switch:
```

### Sensors

ESPHome sensors can be mapped to certain cluster attributes. For example the `TemperatureMeasurement` cluster has a `MeasuredValue` attribute that represents a temperature

#### Boolean state

The `contact` option maps an ESPHome binary sensor to the `StateValue` attribute of the `BooleanState` cluster. Compatible device types are `contact_sensor`, `water_freeze_detector`, `water_leak_detector`, and `rain_sensor`.

```yaml
matter:
  endpoints:
    1:
      contact_sensor:
        contact: contact_id
```

#### Occupancy

The `occupancy` option maps an ESPHome binary sensor to the `Occupancy` attribute of the `OccupancySensing` cluster. Compatible device types are `occupancy_sensor`, `camera`, `snapshot_camera`, and `ambient_context_sensor`.

```yaml
matter:
  endpoints:
    1:
      occupancy_sensor:
        occupancy: occupancy_id
```

#### Temperature

The `temperature` option maps an ESPHome sensor in degrees Celsius to the `TemperatureMeasurement` cluster. Compatible device types are `air_quality_sensor`, `soil_sensor`, `temperature_controlled_cabinet`, `room_air_conditioner`,`smoke_co_alarm`, `cook_surface`, `temperature_sensor`, `pump`, and `evse`.

```yaml
matter:
  endpoints:
    1:
      temperature_sensor:
        temperature: temperature_id
```

#### Relative humidity

The `relative_humidity` option maps an ESPHome sensor reporting a percentage to the `RelativeHumidityMeasurement` cluster. Compatible device types are `air_quality_sensor`, `room_air_conditioner`, `smoke_co_alarm`, `humidifier_dehumidifier`, and `humidity_sensor`.

```yaml
matter:
  endpoints:
    1:
      humidity_sensor:
        relative_humidity: humidity_id
```

#### Illuminance

The `illuminance` option maps an ESPHome sensor in lux to the `IlluminanceMeasurement` cluster. Use it with `light_sensor`.

```yaml
matter:
  endpoints:
    1:
      light_sensor:
        illuminance: illuminance_id
```

#### Pressure

The `pressure` option maps an ESPHome sensor in hectopascals to the `PressureMeasurement` cluster. Compatible device types are `pressure_sensor` and `pump`.

```yaml
matter:
  endpoints:
    1:
      pressure_sensor:
        pressure: pressure_id
```

#### Flow

The `flow` option maps an ESPHome sensor in cubic metres per hour to the `FlowMeasurement` cluster. Compatible device types are `flow_sensor` and `pump`.

```yaml
matter:
  endpoints:
    1:
      flow_sensor:
        flow: flow_id
```

#### Soil moisture

The `soil_moisture` option maps an ESPHome sensor reporting a percentage to the `SoilMeasurement` cluster. Use it with `soil_sensor`.

```yaml
matter:
  endpoints:
    1:
      soil_sensor:
        soil_moisture: soil_moisture_id
```

#### Air-quality concentrations

Matter defines a separate concentration-measurement cluster for each pollutant. The clusters are automatically created when a sensor is mapped to them.

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

#### Electrical measurements

The `electrical_sensor` device type requires `with_clusters` to contain at least one
of `electrical_power_measurement` or `electrical_energy_measurement`.

```yaml
matter:
  endpoints:
    1:
      electrical_sensor:
        # At least one of ElectricalPowerMeasurement or ElectricalEnergyMeasurement
        # must be enabled for electrical_sensor to be valid.
        with_clusters:
          ["ElectricalEnergyMeasurement", "ElectricalPowerMeasurement"]
        # Energy measurements are reported as structs with additional information such as timestamps. This is
        # not supported by esphome-matter yet but is a planned feature.
        # Power:
        voltage: voltage_id
        active_current: current_id
        reactive_current: current_id
        apparent_current: current_id
        active_power: power_id
        reactive_power: power_id
        apparent_power: power_id
        rms_voltage: voltage_id
        rms_current: current_id
        rms_power: power_id
        frequency: frequency_id
        power_factor: power_factor_id
        neutral_current: current_id
```
