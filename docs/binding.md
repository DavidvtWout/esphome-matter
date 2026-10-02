Each device on a Matter fabric is called a node and has a unique id. Commands are send to specific node IDs, but this introduces a problem. How does for example a button know the ID of the light it should send commands to? This is what binding is used for. This feature is also present in Zigbee and Matter binding support is almost identical.

Binding involves a client and a cluster node. The most straightforward example is a light and a button. In this case the light is the server node and the button the client node.

Binding essentially means that the client device keeps a list of NodeIDs of the devices it's bound to. The Binding cluster is used for this. If a device type that supports binding is added to an endpoint, the Binding cluster (0x001E) is automatically created. In esphome-matter these device types are the `on_off_light_switch`, `dimmer_switch`, and `color_dimmer_switch`. Furthermore, the `control_bridge`, `pump_controller`, `thermostat_controller` and `closure_controller` also automatically create the Binding cluster, but these device types are still untested.

Whenever a command is triggered, the device sends a command to each NodeID that were added to its Binding cluster.

For a list of available Matter commands, see [actions.md](./actions.md)

# How to bind devices

Binding is delegated by the Matter controller. The exact steps depend on the controller. For matterjs-server (the controller used by homeassistant) you should navigate to the endpoint of the client device you want to bind. Here you find a "Bindings" list with an "Add Binding" option.

# Access Control List

Nodes can't just send commands to any other node on the fabric. This would be a security issue if one of the devices gets compromised. To prevent this, Matter keeps track of an Access Control List (ACL). The AccessControl cluster (0x001F) is located on endpoint 0 of all devices. After commissioning a device, only the controller is usually in the ACL so commands originating from other nodes are ignored.

In the button/light example, during binding, the Matter controller should add the NodeID of the button to the ACL of the light to allow it to accept the commands the button sends. This is done automatically so normally you shouldn't do anything with the ACL cluster manually. But if binding doesn't work it's a good idea to check the ACL cluster first.

Devices must support at least 5 entries in their ACL but more is also possible. If binding fails with some obscure error it's very possible that the ACL is full. Some controllers (for example matterjs-server) support manually removing enties from the ACL to create more space. As a last resort you can also factory-reset a device and start over.

Keep in mind that binding is fabric-specific. If a device has joined multiple fabrics, each fabric "sees" a different ACL and Binding cluster.

# Groups

Binding to multiple devices has a drawback. A command is sent to each individual node and in case of lights this can cause the well-known "popcorn effect" where there is a visible delay between lights turning on and off. Matter solves this by creating device groups. A new group ID is created and instead of binding to each individual NodeID, the button is bound to a single GroupID. In this case, esphome-matter sends out a multicast

Binding an esphome-matter device to groups is supported but has not been tested yet. Grouping esphome-matter devices should also be supported but is also untested.

# WiFi/Thread

It's possible to bind WiFi and Thread devices as long as the Thread border router is configured correctly.
