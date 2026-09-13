Each endpoint is defined by its ID which can range from 0 to 65534. An endpoint at id 0 with device type `Root Node` is always created. This device type defines clusters such as `AccessControl`, `BasicInformation`, diagnostic clusters and clusters that are used for commissioning.

Beneath an endpoint are clusters. Clusters are collections of attributes and commands with more or less a single function. For example the `OnOff` cluster defines attributes such as the state, startup behaviour and defines commands such as `on`, `off` and `toggle`.

# Device types

To make cluster management more convenient, Matter defines device types. For example, the `Dimmable Light` creates clusters such as `OnOff` and `LevelControl`. Different device types may define the same clusters, so if you're not sure, it's best to assign only a single device type to each endpoint.

For all supported device types, see the documentation on [device types](device-types.md).
