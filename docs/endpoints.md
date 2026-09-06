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

Most clusters are supported by multiple device types. The `TemperatureMeasurement` cluster is supported by 9 device types with the simplest being the `Temperature Sensor`.

```yaml
matter:
  endpoints:
    1:
      temperature_sensor:
        temperature: sensor_id
```

##### BooleanState

Device types: `contact_sensor`, ...

##### ElectricalEnergyMeasurement

##### ElectricalPowerMeasurement

```yaml
matter:
  endpoints:
    1:
      electrical_sensor:
        with_clusters: ["ElectricalPowerMeasurement"]
        voltage: sensor_id
        active_current: sensor_id
        reactive_current: sensor_id
```

##### TemperatureMeasurement

Device types: `air_quality_sensor`, `cook_surface`, `evse`, `pump`, `room_air_conditioner`, `smoke_co_alarm`, `soil_sensor`, `temperature_controlled_cabinet`, `temperature_sensor`

```yaml

```
