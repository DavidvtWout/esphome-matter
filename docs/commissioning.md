Because ESPHome already provides Wi-Fi or Thread credentials, commissioning works differently from most Matter devices.

After flashing the device, a commission code is generated and shown (SetupQRCode). Copy this code or click the link and scan the QR-code.

```
[C][matter]: Matter:
[C][matter]:   SetupQRCode: MT:Y.K904QI14-O992WI00
[C][matter]:   QR URL: https://project-chip.github.io/connectedhomeip/qrcode.html?data=MT:Y.K904QI14-O992WI00
[C][matter]:   Manual pairing code: 32552014321
[C][matter]:   Commissioning window: open
[C][matter]:   Fabrics: none
```

# Commissioners

### matterjs-server / Home Assistant

To accept the dev DAC that esphome-matter uses, matterjs-server should be started with the `--enable-test-net-dcl` argument set to `true`;

`matterjs-server --enable-test-net-dcl=true`

Or the `ENABLE_TEST_NET_DCL` environment variable should be set to `true`.

For the Home Assistant Matter Server app, enable **Enable test-net DCL usage**
under **Settings → Apps → Matter Server → Configuration**. Save and restart
the Matter Server app so the running server uses the setting. This was needed
when commissioning the cover canary with matterjs-server.

When commissioning, use the "Commission existing device" option;

![matterjs-server-commission.png](img/matterjs-server-commission.png)

### python-matter-server

Accepts the dev DAC without any problems. But python-matter-server is discontinued and replaced by matterjs-server.

##### IKEA Dirigera

In the IKEA Home smart app, add the device by opening the QR url and scanning the code.

The IKEA system doesn't like it when a device has multiple endpoints. With the example config where a button, temperature sensor and light are configured, only the temperature sensor is shown in the app. If only the light endpoint is configured, it is detected correctly as a light.

# Persistence

The SetupQRCode is stored in flash and survives OTA updates. For a device with
no stored fabrics, restarting reopens the initial commissioning window for
15 minutes. Once the device has a fabric, a restart does not reopen that
window: use the controller's sharing flow and its temporary code to add another
controller. The original code can be used again after a Matter factory reset.

The fabric data is also stored on flash (nvs partition) and also survives ota updates. The fabric itself is independent of the hardware layer (wifi or thread). This means that it's even possible to commission a device over wifi and later substitute the wifi component with openthread (as long as the hardware supports both) and you don't need to re-commission!

The Shelly cover canary retained its Apple Home and Home Assistant fabrics
when switching from Wi-Fi to Thread. Keep the NVS partition and endpoint IDs
stable across OTA updates. After a Thread reboot, check both the native
ESPHome service and each fabric's operational Matter service; see
[Thread debugging](dev/thread-debugging.md#commissioned-devices-after-reboot).

## Covers with native Home Assistant control

A cover can use Apple Home through Matter and Home Assistant through the
native ESPHome API. Enable `api:`, keep the backend cover internal, and expose
the coordinated `cover: platform: matter` entity. Home Assistant's ESPHome
integration then provides position, tilt, Stop, and tilt-open/tilt-close
services without joining an additional Matter fabric.

Home Assistant Matter commissioning remains optional for this setup. If it
was already commissioned, its Matter entity and the native ESPHome entity are
separate representations of the same blind. See [covers](covers.md) and the
[Dashboard guide](dashboard-covers.md) for the configuration.

# Multiple fabrics

Up to 5 fabrics are supported by default, but if needed, this can be increased with the `CONFIG_MAX_FABRICS` sdkconfig option:

```yaml
esp32:
  framework:
    type: esp-idf
    sdkconfig_options:
      CONFIG_MAX_FABRICS: # Set to anything from 5 to 255
```
