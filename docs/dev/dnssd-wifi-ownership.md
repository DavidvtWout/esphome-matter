# DNS-SD / mDNS under ESPHome WiFi ownership

## The problem

Matter commissioning over Wi-Fi requires the device to advertise `_matterc._udp`
(and after commissioning `_matter._tcp`) via mDNS. When those records are absent, any
Matter controller that tries to commission on-network will simply never find the device.

In a normal esp-matter project this works out of the box. In an ESPHome project it
doesn't, because of two interacting constraints:

1. **ESPHome owns the Wi-Fi driver.** CHIP's `ConnectivityManagerImpl_WiFi` must be
   compiled out (`CONFIG_ENABLE_WIFI_STATION=n`, `CONFIG_ENABLE_WIFI_AP=n`); otherwise
   it calls `esp_wifi_start()` / `esp_wifi_connect()` and races ESPHome's wifi
   component, producing `ESP_ERR_WIFI_STOP_STATE` and an endless "Restarting adapter"
   loop that prevents the interface from ever associating.

2. **CHIP's DNS-SD backend is gated by connectivity flags.** All real implementations
   of `ChipDnsd*()` in `connectedhomeip/src/platform/ESP32/DnssdImpl.cpp` are inside
   `#if CHIP_DEVICE_CONFIG_ENABLE_WIFI || CHIP_DEVICE_CONFIG_ENABLE_ETHERNET`. With
   both flags at 0, every function compiles to a no-op or returns
   `CHIP_ERROR_INCORRECT_STATE`. CHIP's `DiscoveryImplPlatform` advertiser stays in
   `kInitializing` forever.

The two constraints together form a closed loop: disabling CHIP's WiFi manager (required
for ESPHome compatibility) also disables the only DNS-SD backend that works at runtime.

---

## Approaches tried and why they failed

### 1. `CONFIG_USE_MINIMAL_MDNS=y`

CHIP has a built-in ("minimal") mDNS implementation that doesn't depend on
`CHIP_DEVICE_CONFIG_ENABLE_WIFI`. Enable it and the flag gate disappears.

**Why it fails:** CHIP's minimal mDNS tries to bind UDP port 5353. ESP-IDF's
`espressif/mdns` component (used by ESPHome) already holds that socket, and it binds
without `SOF_REUSEADDR` (`mdns_networking_lwip.c:43`). The second bind returns LwIP
`ERR_USE` (value 8), which bubbles up as:

- `0x3000008` — `CHIP_ERROR` range `kLwIP` (byte `0x03`) + LwIP error value 8
- `0x46` = `CHIP_ERROR_NO_ENDPOINT` — cascade from the bind failure

The port conflict is structural; there is no socket option that fixes it without
modifying ESP-IDF mdns source.

### 2. `CONFIG_ENABLE_ETHERNET_TELEMETRY=y`

Setting this Kconfig flag sets `CHIP_DEVICE_CONFIG_ENABLE_ETHERNET=1`, which unblocks
the `#if` gate in `DnssdImpl.cpp` and makes `EspDnssdInit` / `EspDnssdPublishService`
compile as real code — without requiring CHIP to own Wi-Fi.

**Why it fails on ESP32-C6:** CHIP's Kconfig (`config/esp32/components/chip/Kconfig`)
defines `GPIO_RANGE_MAX` as a range-constrained integer with `depends on
ENABLE_ETHERNET_TELEMETRY`, but only provides `default` values for ESP32, S2, C3, S3,
and H2. ESP32-C6 has no matching `default`. When `ENABLE_ETHERNET_TELEMETRY=y` on
ESP32-C6, the symbol is active but `str_value = ''`. kconfgen's `write_json_menus()`
then hits `int('', 10)` → `ValueError: invalid literal for int() with base 10: ''`.
This crash is in kconfgen's Kconfig tree introspection (menu serialization), not user
value resolution, so setting `GPIO_RANGE_MAX` in `sdkconfig.defaults` or via
`add_idf_sdkconfig_option()` does not help — the crash happens before any user values
are read.

Additionally, even if the build succeeded, `EspDnssdPublishService()` calls
`mdns_hostname_set(service->mHostName)` where `mHostName` is CHIP's MAC-derived
hostname. This would silently overwrite ESPHome's configured device hostname for all
mDNS services (including `_esphomelib._tcp`), making them advertise under the wrong
name.

And `ESPEthernetDriver::Init()` (compiled in by the same flag) attempts to initialize
an IP101 PHY chip via GPIO (MDC/MDIO/RST pins). ESP32-C6 has no RMII Ethernet MAC
peripheral; this would fail or corrupt GPIO state.

---

## The solution: linker-override DNS-SD

The linker prefers strong-symbol definitions from application `.o` files over weak
symbols or archive members. CHIP links its platform libraries as `--whole-archive`
archives, but application-layer `.o` files take precedence for symbols defined in both
places.

`matter_dnssd.cpp` (compiled by PlatformIO's SCons pass as part of the `src`
component) defines all `chip::Dnssd::ChipDnsd*()` functions as real implementations
that call `espressif/mdns` directly. At link time the linker picks these over the
no-op stubs in `DnssdImpl.cpp`, bypassing all Kconfig gates without touching any CHIP
source and without any sdkconfig changes.

### Key design decisions

**No `mdns_hostname_set()` call.** The original `EspDnssdPublishService()` clobbers
the device hostname. We deliberately omit this; Matter services are registered under
ESPHome's hostname, keeping `_matterc._udp` and `_esphomelib._tcp` consistent.

**`mdns_init()` is idempotent.** ESPHome's mdns component already called it; calling
it again in `ChipDnssdInit` is safe and required by the CHIP platform API.

**Remove by type, not instance name.** CHIP generates a fresh random 64-bit instance
name (e.g. `19CD1A9C30FBC089`) on every re-advertise cycle. Removing only the specific
instance name before re-adding leaves stale instances from prior cycles in the mDNS
responder. `ChipDnssdPublishService` instead removes all instances of the service type
(`while mdns_service_exists(...) mdns_service_remove(...)`) before adding the new one.

**Subtypes must be registered explicitly.** Matter controllers do not browse
`_matterc._udp` directly — they query the discriminator subtype
`_L<discriminator>._sub._matterc._udp.local.` (and `_S<short>`, `_CM`, `_V<vendor>`).
CHIP passes these in `service->mSubTypes`. Without calling
`mdns_service_subtype_add_for_host()` for each, the device is invisible to the
commissioner even though `_matterc._udp` is correctly advertised. This was the last
remaining commissioning blocker.

**Network up-edge bridge.** With CHIP's WiFi manager compiled out, CHIP never
receives the IP-up event that normally drives `DnssdServer::StartServer()`.
`MatterComponent::loop()` watches `network::is_connected()` and on the rising edge
posts `kDnssdRestartNeeded` via `PlatformMgr().PostEventOrDie()`, which triggers
the same re-advertise path.

**Global IPv6 re-advertisement.** The first mDNS announcement goes out as soon as WiFi
connects, before IPv6 SLAAC completes, so the initial records contain only the A
record. `MatterComponent::setup()` registers an `IP_EVENT_GOT_IP6` handler that posts
another `kDnssdRestartNeeded` once a global unicast address (`2000::/3`) is assigned,
ensuring the updated announcement includes the AAAA record. Link-local (`fe80::/10`)
assignments are ignored — they trigger the event first but are not usable without
interface scope information on the commissioner side.
