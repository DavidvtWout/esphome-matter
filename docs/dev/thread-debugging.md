### OpenThread BorderRouter (OTBR)

If you run OTBR you have access to the following commands.

`ot-ctl srp server host` can be used to find the IPv6 address of the esphome device;

```
# ot-ctl srp server host
<esphome-device-name>.default.service.arpa.
    deleted: false
    addresses: [fd87:...]
    lease: 7200
    key-lease: 680400
    remaining lease: 6848.955
    remaining key-lease: 682048.955
```

`ot-ctl srp server service` finds the services and the output should look like this for a commissioned device;

```
# ot-ctl srp server service
<fabrid-id>-<node-id>._matter._tcp.default.service.arpa.
    subtypes: _I<fabrid-id>
    port: 5540
    TXT: [...]
    host: <esphome-device-name>.default.service.arpa.
    addresses: [fd87:...]
    ...
<esphome-device-name>._esphomelib._tcp.default.service.arpa.
    port: 6053
    ...
```

And like this for an uncommissioned device;

```
# ot-ctl srp server service
<esphome-device-name>._esphomelib._tcp.default.service.arpa.
    port: 6053
    ...
<something>._matterc._udp.default.service.arpa.
    ...
```

Sadly, `ot-ctl` is pure trash and shows deleted records for a whole week and doesn't allow you to filter on anything. So I would recomment to enable [SRP Advertising Proxy](https://deepwiki.com/openthread/ot-br-posix/6.3-srp-advertising-proxy) in OTBR (I think this is done for most builds anyway?). This proxies the SRP services to the backbone interface via mdns. These can then be discovered with `mdns-scanner`, `avahi-browse` or other mdns discovery tools.

### Commissioned devices after reboot

Check that each retained fabric has an operational `_matter._tcp` service,
in addition to the ESPHome `_esphomelib._tcp` service. A reachable ESPHome API
alone does not confirm that a Matter controller can rediscover the device.

ESPHome manages the OpenThread stack and SRP client. The Matter component
therefore disables `CONFIG_ESP_MATTER_ENABLE_OPENTHREAD` to prevent esp-matter
from initializing a second stack. In esp-matter 1.6, that setting also skips
the startup advertisement of stored fabrics. The component explicitly
schedules `DnssdServer::StartServer()` on the Matter task after
`esp_matter::start()` succeeds. Its DNS-SD bridge then adds the operational
services to ESPHome's existing SRP client.

After a Wi-Fi-to-Thread update, controllers may temporarily hold the old
address or subscription. Confirm the new IPv6 service records and a resumed
Matter session before diagnosing the cover mapping itself. On the Shelly
cover canary, the corrected startup advertised all retained fabrics and the
native API, and the user confirmed movement over Thread on 2026-10-01.

### Cover state over Thread

Compare the backend/native ESPHome position with Window Covering's
`CurrentPositionLiftPercent100ths` and `CurrentPositionTiltPercent100ths`,
and compare the requested destination with the two `TargetPosition` attributes.
ESPHome uses `1.0 = open`; Matter uses `0 = open` and `10000 = closed`.
Opening/closing comes from `OperationalStatus`, independently of the target.

Current positions should follow backend publications while moving. A
controller's slider can still show its requested destination; that was observed
in Apple Home while Home Assistant showed current-position updates. See
[cover reporting](../covers.md#position-reporting) and the
[Dashboard physical button checks](../dashboard-covers.md#3-connect-and-test-the-physical-buttons).
