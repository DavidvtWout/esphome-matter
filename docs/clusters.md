A device type defines one or more clusters that it requires. For example, the `temperature_sensor` requires the `TemperatureMeasurement` cluster to be created on the endpoint it's added to.

### Descriptor

As the name suggests, this cluster describes the endpoint. Among other things, this endpoint contains an attribute that lists all the device types on this endpoint. This cluster is automatically created, and esphome-matter does not provide you any control over this cluster.

### Identify

This cluster is present on almost all device types. The `Identify` command can be sent to it which, for example, for a light device makes it blink.

# Measurement clusters

# Light clusters

# Switch clusters

# Cover clusters

## WindowCovering

The `window_covering` device type creates this cluster. An ESPHome `cover_id`
mapping updates current lift and optional tilt positions, accepts target
positions and Stop, and publishes lift/tilt operational status.

Matter positions use `Percent100ths`: `0` is open and `10000` is closed, the
reverse of ESPHome's normalized convention. Current positions follow backend
state publications; target positions describe the requested destination.
For a single-motor Venetian blind, the coordinator performs lift before tilt.

See [covers](covers.md) for supported features and the native ESPHome API
entity, and [Window Covering commands](generated/commands.md#windowcovering) for
outgoing command syntax. Absolute-position commands are not supported by
mapped ESPHome covers.

# Other
