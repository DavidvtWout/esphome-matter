# Venetian blind backend contract

This contract describes the representative ESPHome backend used to design the
Matter Window Covering adapter. Device names, Home Assistant entity IDs, Thread
credentials, and commissioning data are intentionally omitted.

## Version inventory

- ESPHome: `2026.8.2` for the deployed hardware canary; the initial backend
  inventory used `2026.7.4`
- ESP-IDF: `5.5.5`
- ESP-Matter component: `davidvtwout/esp_matter` `1.6.0~2`
- ESP-Matter component hash from the resolved build:
  `67c766e062ed460c9d54dce13d251f0e6b665afae93e4b72322eb7b1327cb73d`
- Venetian blind component:
  `bruxy70/Venetian-Blinds-Control` commit
  `41abbe36877efa85db346913bf4b889aca72b643`
- Hardware family: ESP32-C6 Shelly 2PM Gen4 configuration

The deployed canary and the public Dashboard example pin the Venetian backend
to the commit above. Keep that pin when reproducing the hardware test so a
rebuild uses the same motor behavior.

See [covers](covers.md) for user configuration and
[Dashboard setup](dashboard-covers.md) for Git sources and an existing Shelly
hardware package.

## Cover semantics

The `venetian_blinds` cover reports normalized, time-estimated state:

| Value | ESPHome position | ESPHome tilt | Matter percent100ths |
|---|---|---|---|
| Fully open | `1.0` | `1.0` | `0` |
| Midpoint | `0.5` | `0.5` | `5000` |
| Fully closed | `0.0` | `0.0` | `10000` |

Position and tilt are estimates derived from configured travel times. They are
not encoder measurements. The representative device uses separate open and
close travel durations and a `2300ms` full tilt duration.

The component advertises position, tilt, and Stop. It publishes progress once
per second while moving and publishes a final state after reaching a target or
processing Stop. Local wall-button actions use the same ESPHome cover API, so
their state publications reach the Matter mapping.

The generic ESPHome cover state callback does not identify why a cover became
idle. The adapter can cancel a deferred tilt when a local Stop ends lift before
its requested target, but it cannot distinguish a local Stop exactly at that
target from normal completion. Route every local Stop through
`matter.cover.cancel_pending` immediately before `cover.stop`; this explicit
action invalidates pending Matter work before ESPHome publishes the stopped
state. Matter's own Stop command already establishes the same barrier. Do not
enable combined lift-and-tilt operation on a device with local Stop paths that
bypass this action.

## Shared-motor command behavior

Lift and tilt share one motor. A position movement first rotates the slats in
the movement direction and then changes lift. A tilt-only movement preserves
the current lift estimate.

The backend does not safely implement a single `CoverCall` containing both a
position and tilt target: its tilt branch replaces the position target selected
by its position branch. The Matter adapter therefore coalesces the two Matter
callbacks and sequences them as follows:

1. move lift to the requested position;
2. wait for the backend to publish an idle state;
3. adjust tilt to the requested final angle, if needed.

Rapid Matter and native API updates use bounded, last-value pending state for
each axis. Stop clears all older pending movement, runs on the ESPHome main
loop, and reconciles Matter targets only after the backend publishes its
stopped state.
When Home Assistant requests a new tilt while lift is already moving, the
adapter accepts the request but does not try to move both axes at once. It keeps
the newest tilt target and applies it after lift becomes idle (unless a newer
Stop or movement supersedes it).

## Relay and control boundaries

The adapter calls only `Cover::make_call()`. Relay interlocking, thermal and
power protection, timing, and calibration remain in the existing cover and
switch configuration.

For a local button Stop, call the Matter cancellation action before stopping the
ESPHome cover:

```yaml
on_release:
  then:
    - matter.cover.cancel_pending:
        cover_id: venetian_blinds
    - cover.stop: venetian_blinds
```

Apply this ordering to every local Stop automation, including scripts and
physical button handlers. Mark the mapped cover `internal: true` so a direct
Home Assistant ESPHome API command cannot bypass the signal. To expose native
ESPHome control alongside Matter, add a coordinated cover entity:

```yaml
cover:
  - platform: matter
    id: native_blind
    name: Native Blind
    device_class: blind
    cover_id: venetian_blinds
```

Here `venetian_blinds` is the existing internal backend mapped by the Matter
Window Covering endpoint. Give the native entity a different name from the
backend so ESPHome web requests select the coordinated entity. The native
entity mirrors backend position, tilt, and operation publications. Its calls
share the Matter command queue: a native Stop invalidates pending Matter lift
and tilt work; a compound native lift/tilt call completes lift before tilt.
Native movement also updates Matter target attributes, guarded by the same
command generations. State synchronization does not restore motor targets.
Native control can run before Matter initialization succeeds, while Matter
attribute writes wait for successful initialization.

Local Stop automations acting directly on the backend still need the explicit
cancellation action above. Route any other direct control path through the
coordinated native entity, or notify cancellation immediately before Stop.

The representative YAML switches the opposite relay off before energizing a
direction and does not configure an explicit reversal dead time. Check the
motor/controller requirements when using another blind; the adapter does not
add relay timing or replace the hardware/backend protections.

The Home Assistant child-lock helper currently gates local button handlers.
It does not gate remote Matter commands. If remote lockout is required, it must
be added deliberately below the Matter adapter so every remote control path has
the same policy.

## Hardware evidence

The Shelly 2PM Gen4 (ESP32-C6) canary passed lift, tilt, and Stop with Apple
Home through Matter and Home Assistant through the native ESPHome API. The
Wi-Fi checks were completed on 2026-09-30; the user confirmed operation over
Thread on 2026-10-01. The Wi-Fi-to-Thread update preserved commissioning, and
the device advertised its native API and retained Matter fabrics afterward.

The canary has no wired wall buttons. Physical button interruption and
retargeting to the current position during motion remain checks for the next
hardware test. Keep firmware backups, addresses, credentials, and detailed
device logs in private deployment records.

### Record for each additional device

Before flashing another deployed blind, record privately:

- exact device model/revision and flash partition layout;
- known-good firmware binary and configuration backup;
- serial/recovery access and a rollback procedure;
- Thread border router and controller versions;
- measured meaning of tilt `0.0`, `0.5`, and `1.0` on the physical slats;
- reversal behavior, including any motor-controller-enforced dead time;
- interruption tests for lift, tilt, combined lift-then-tilt, and Stop.

## First-cover test sequence

The native command-queue tests cover latest-value coalescing, Stop barriers,
detached-work invalidation, and per-axis generations. They do not emulate the
full ESPHome backend or Matter-thread scheduler; hardware tests exercise those
combined lift/tilt transitions. The completed canary provides evidence for its
specific backend, firmware, and controllers. When testing another cover, keep
a known-good firmware/configuration backup and recovery procedure, and verify
one device at a time:

1. Commission the cover and check reported lift/tilt positions without moving
   it.
2. Test a small lift movement and Stop, then a small tilt movement and Stop.
3. While lift is moving, send multiple tilt targets and verify only the newest
   one runs after lift settles.
4. During combined movement, use every wired local Stop path and verify lift
   and deferred tilt both remain stopped; repeat with a Matter Stop and a
   native ESPHome Stop. Include a button release near lift completion.
5. Retarget to the current position during motion and verify the earlier
   destination is canceled.
6. Check lift/tilt operational states and Matter target attributes after local
   movement, stop, and normal completion.

Stop the test if relay interlocking, position estimates, slat orientation, or
Matter state diverges from the physical cover. Record the result and any
remaining checks before expanding to more blinds.
