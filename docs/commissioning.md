Because ESPHome already provides Wi-Fi or matter credentials, commissioning works in a different way than you're probably used to with other matter devices.

After flashing the device, a commission code is generated and shown (SetupQRCode). Copy this code or click the link and scan the QR-code.

![commission-code.png](img/commission-code.png)

In your matter controller you need to select the on-network commissioning option. In `python-matter-server` this is called "Commission existing device":

![matter-server-commission.png](img/matter-server-commission.png)


### Multiple fabrics
`connectedhomeip` supports 5 fabrics by default (can be configured with the `CONFIG_MAX_FABRICS` option added to `esp32.framework.sdkconfig_options`) so `esphome-matter` also has support for multiple fabrics. However, currently there is no way to re-open the commissioning window. It's not that hard to implement and will be added in the future.
