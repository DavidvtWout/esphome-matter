# Covers in ESPHome Dashboard

Dashboard can download the Matter component directly from Git, just as it
downloads the external `venetian_blinds` component. The cover implementation
and its native ESPHome platform are both included in `components: [matter]`.
No local checkout or manual component copy is required on the Dashboard host.

The cover work is published on the fork branch
[`mrflo97/esphome-matter@vb-02-03-cover-schema`](https://github.com/mrflo97/esphome-matter/tree/vb-02-03-cover-schema).
The example pins the tested implementation to commit
[`2bce176054874102d8e4690e643d62f88a0a1954`](https://github.com/mrflo97/esphome-matter/commit/2bce176054874102d8e4690e643d62f88a0a1954).
Use that revision for this hardware test; the upstream `main` branch is not
the source of the tested cover changes.

The hardware canary used **ESPHome 2026.8.2** with **ESP-IDF** and
`esp32.toolchain: platformio`. Use those settings to reproduce its build.
Other Dashboard versions have not been verified on this physical cover.

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
- the coordinated `cover1_api` entity named `${cover1_name} ESPHome`.

The source configuration is:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/mrflo97/esphome-matter
      ref: 2bce176054874102d8e4690e643d62f88a0a1954
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
validation/build. Both sources use full commit SHAs with `refresh: never`
so rebuilding uses the same component revisions. To follow subsequent Matter
development, change its `ref` to `vb-02-03-cover-schema` and its `refresh` to
`5min`. Keep the Venetian backend pinned to its tested commit.

After editing, use Dashboard's **Validate** and then **Install** actions. If
you follow the branch and it was just updated, temporarily use `refresh: 0s`
for one validation if the cache has not refreshed yet, or select the new commit
SHA. Changing a ref selects a separate external-component cache. **Clean Build
Files** is useful for a stale compiled build; it does not select a newer Git
revision.

See ESPHome's [external component documentation](https://esphome.io/components/external_components/)
and [package documentation](https://esphome.io/components/packages/) for the
source caching and `!extend` behavior.

## 3. Connect and test the physical buttons

Use Home Assistant's **ESPHome integration** for the `${cover1_name} ESPHome`
entity. It provides native position, tilt, Stop, and tilt-open/tilt-close
services without commissioning Home Assistant to Matter.

Commission Apple Home using the setup code printed in the device logs. If the
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
