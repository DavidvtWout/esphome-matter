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
