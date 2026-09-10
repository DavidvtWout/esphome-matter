A device type defines one or more clusters that it required. For example the `temperature_sensor` requires the `temperatureMeasurement` cluster to be created on the endpoint it's added to.

### Descriptor

As the name suggests, this cluster describes the endpoint. Among other things, this endpoint contains an attribute that lists all the device types on this endpoint. This cluster is automatically created and esphome-matter does not provide you any control over this cluster.

### Identify

This cluster is present on almost all device types. The `Identify` command can be sent to it which for example for a light device makes it blink.

# Measurement clusters

# Light clusters

# Switch clusters

# Other
