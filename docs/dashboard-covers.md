# Covers in ESPHome Dashboard

Dashboard can download the Matter component directly from Git, just as it
downloads the external `venetian_blinds` component. The cover implementation
and its native ESPHome platform are both included in `components: [matter]`.
No local checkout or manual component copy is required on the Dashboard host.

During review, use the source revision shown in the example below. When the
cover work is merged upstream, the same configuration can use
`DavidvtWout/esphome-matter`. Pin a reviewed commit when deploying firmware;
following a branch also picks up later configuration and implementation changes.

The source follows upstream's `with_features` option with snake_case feature
names. Earlier cover prototypes used `features` and CamelCase names; update
those configurations when updating the component revision.

The hardware canary used **ESPHome 2026.8.2** with **ESP-IDF** and
`esp32.toolchain: platformio`. Use those settings to reproduce its build.
ESPHome 2026.9.0 has also booted on the device, but one unexplained abort was
reported; the revised component still requires its own hardware checks.

## 1. Prepare the existing hardware package

For a Shelly 2PM Gen4 with an existing working Venetian blind configuration,
copy its local base file to `common/shelly_2pm_gen4_matter_base.yaml` in your
Dashboard configuration directory. This gives the test device its own package
while other devices continue to use their existing base.

Keep the test device's GPIO assignments, relay protections, measured travel
times, child-lock condition, and network configuration. The example below
expects the backend cover ID `cover1`. Adapt the IDs if your base differs.
Wi-Fi and Thread are both supported; the network credentials remain in your
local `secrets.yaml`.

Remove the `external_components:` block from this copied base. The device YAML
below provides both Git sources, replacing any local `../components` path.

In the copied base, replace **both** physical button `on_release` handlers with:

```yaml
on_release:
  - matter.cover.cancel_pending:
      cover_id: cover1
  - cover.stop: cover1
```

Keep the existing `on_press` handlers and their child-lock conditions for the
first physical button test. Any other script that stops `cover1` directly also
needs the cancellation action immediately before Stop. Edit these handlers in
the base itself: adding an `on_release` through `!extend` would append another
automation rather than reliably put cancellation before the existing Stop.

The cancellation action requires a configured Matter component, so keep this
copied base paired with the Matter-enabled device YAML.

## 2. Use the device YAML

Copy [the device example](../examples/shelly-2pm-gen4-venetian-blind.yaml) into
Dashboard. Set the device name, cover name, Home Assistant child-lock helper,
and measured open/close durations for the device you will test. Retain its
existing name when updating an installed ESPHome device.

The example includes your prepared local hardware package and adds:

- Git sources for `matter` and the pinned Venetian backend;
- IPv6 and the native ESPHome API;
- the Matter lift-and-tilt endpoint;
- `internal: true` on the physical backend using `!extend cover1`;
- the coordinated `cover1_api` entity named `${cover1_name} ESPHome`;
- diagnostic text sensors for the stored Matter setup code and QR payload.

The source configuration is:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/mrflo97/esphome-matter
      ref: 578688af444fb5a9c635ab199083712af727899e
    components: [matter]
    refresh: never
  - source:
      type: git
      url: https://github.com/bruxy70/Venetian-Blinds-Control
      ref: 41abbe36877efa85db346913bf4b889aca72b643
    components: [venetian_blinds]
    refresh: never
```

Dashboard obtains the component sources and ESP-IDF build dependencies during
validation/build. Both sources use full commit SHAs with `refresh: never`.
The Venetian pin preserves the tested motor behavior. The Matter pin includes
the reviewed schema and coordinator fixes; those fixes still need a fresh
hardware check. To follow later development, use
`ref: vb-02-03-cover-schema` and `refresh: 5min` for the Matter source.

After editing, use Dashboard's **Validate** and then **Install** actions. If
you follow a branch that was just updated, temporarily use `refresh: 0s`
for one validation if the cache has not refreshed yet, or select the new commit
SHA. Changing a ref selects a separate external-component cache. **Clean Build
Files** is useful for a stale compiled build; it does not select a newer Git
revision.

For hosts with limited RAM, set `esphome.compile_process_limit: 1` to reduce
parallel compilation. Matter's generated cluster code can require substantial
memory; an operating-system-killed compiler needs more available memory or
fewer concurrent jobs.

See ESPHome's [external component documentation](https://esphome.io/components/external_components/)
and [package documentation](https://esphome.io/components/packages/) for the
source caching and `!extend` behavior.

## 3. Connect and test the physical buttons

Use Home Assistant's **ESPHome integration** for the `${cover1_name} ESPHome`
entity. It provides native position, tilt, Stop, and tilt-open/tilt-close
services without commissioning Home Assistant to Matter.

Commission Apple Home using the setup code in Home Assistant's diagnostic
entity `Matter Setup Code`, or the code printed in the device logs. The text
sensor is available through ESPHome without commissioning Home Assistant to
Matter. See [setup-code sensors](commissioning.md#setup-codes-in-home-assistant)
for the YAML and Matter reset button. If the
device already belongs to another Matter fabric, open a sharing/commissioning
window in that controller and use its temporary code. A normal restart only
reopens initial commissioning when no fabrics are stored. See
[commissioning](commissioning.md) for details.

With someone watching the blind, test a short movement first:

1. Press and release each wired direction button; verify release stops motion
   and both Home Assistant and Apple Home receive the resulting state.
2. Start lift from Apple Home, request tilt while lift moves, then stop with a
   physical button release. Verify the waiting tilt never starts afterward.
3. Repeat Stop from the native Home Assistant cover, then from Matter.
4. Check the child-lock helper blocks button presses as before. The existing
   child-lock condition applies to local buttons; it does not block remote
   Matter or native API commands.
5. Reboot and confirm that both the native entity and Apple Home reconnect.
   On Thread, each stored fabric should advertise an operational
   `_matter._tcp` service; see [Thread debugging](dev/thread-debugging.md).

The earlier Shelly canary already passed lift, tilt, and Stop over Wi-Fi and
Thread, but it had no wired buttons. This sequence supplies that remaining
hardware evidence. Use the [backend test sequence](venetian-blind-backend-contract.md#first-cover-test-sequence)
for retargeting and additional interruption checks.
