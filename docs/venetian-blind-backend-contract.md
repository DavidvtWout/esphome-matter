# Venetian blind backend contract

This contract describes the representative ESPHome backend used to design the
Matter Window Covering adapter. Device names, Home Assistant entity IDs, Thread
credentials, and commissioning data are intentionally omitted.

## Version inventory

- ESPHome: `2026.7.4`
- ESP-IDF: `5.5.5`
- ESP-Matter component: `davidvtwout/esp_matter` `1.6.0~2`
- ESP-Matter component hash from the resolved build:
  `67c766e062ed460c9d54dce13d251f0e6b665afae93e4b72322eb7b1327cb73d`
- Venetian blind component:
  `bruxy70/Venetian-Blinds-Control` commit
  `41abbe36877efa85db346913bf4b889aca72b643`
- Hardware family: ESP32-C6 Shelly 2PM Gen4 configuration

The deployed configuration currently requests the Venetian component's moving
`master` branch. Pin the commit above, or another deliberately tested commit,
before canary rollout so a rebuild cannot silently change motor behavior.

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

Rapid Matter updates use bounded, last-value pending state for each axis. Stop
clears all older pending movement, runs on the ESPHome main loop, and reconciles
Matter targets only after the backend publishes its stopped state.

## Relay and control boundaries

The adapter calls only `Cover::make_call()`. Relay interlocking, thermal and
power protection, timing, and calibration remain in the existing cover and
switch configuration.

The representative YAML switches the opposite relay off before energizing a
direction, but it does not currently configure a reversal dead time. That is a
hardware/backend decision and must be verified before physical Matter tests;
the Matter adapter must not be treated as the motor-safety layer.

The Home Assistant child-lock helper currently gates local button handlers.
It does not gate remote Matter commands. If remote lockout is required, it must
be added deliberately below the Matter adapter so every remote control path has
the same policy.

## Remaining canary evidence

Before flashing a deployed blind, record privately:

- exact device model/revision and flash partition layout;
- known-good firmware binary and configuration backup;
- serial/recovery access and a rollback procedure;
- Thread border router and controller versions;
- measured meaning of tilt `0.0`, `0.5`, and `1.0` on the physical slats;
- reversal behavior, including any motor-controller-enforced dead time;
- interruption tests for lift, tilt, combined lift-then-tilt, and Stop.
