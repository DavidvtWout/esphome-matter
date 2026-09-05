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

##### Binding

Endpoints with switch device types get the Binding cluster (id 30) by default.
Set `enable_binding: false` on an endpoint to disable that default, or
`enable_binding: true` to add the Binding cluster to another endpoint. Some
Matter controllers such as matterjs-server allow binding from the UI.

See [docs/actions.md](./docs/actions.md) for a list of available commands on each cluster.

### Sensors

```yaml
temperature_sensor:
  sensor_id: # Point to the ID of a temperature sensor
```
