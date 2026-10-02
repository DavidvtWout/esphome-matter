# Covers

The `window_covering` device type maps an existing ESPHome cover to Matter.
The backend continues to own motor control, relay interlocking, travel times,
calibration, and protection. Matter and the optional native ESPHome entity
share a command coordinator for lift, tilt, and Stop.

For an existing Shelly 2PM Gen4 configuration, start with the
[ESPHome Dashboard guide](dashboard-covers.md) and its
[device YAML example](../examples/shelly-2pm-gen4-venetian-blind.yaml).

## Supported mappings

| Cover | Required `with_features` | `end_product_type` |
|---|---|---|
| Lift only | `lift`, `position_aware_lift` | `roller_shade` (default) |
| Lift and tilt | `lift`, `position_aware_lift`, `tilt`, `position_aware_tilt` | `interior_venetian_blind` (default) or `exterior_venetian_blind` |

The backend must support position and Stop; a lift-and-tilt mapping must also
support tilt. These capabilities are checked during device setup. Mapped covers
do not support `absolute_position`, tilt-only feature combinations, or arbitrary
combinations of the features above.

### Lift-only cover

Use the ID of your existing position-aware ESPHome cover:

```yaml
matter:
  endpoints:
    1:
      window_covering:
        cover_id: roller_cover
        end_product_type: roller_shade
        with_features:
          - lift
          - position_aware_lift
```

### Venetian blind

Use the ID of the physical backend, for example a `venetian_blinds` cover:

```yaml
matter:
  endpoints:
    1:
      window_covering:
        cover_id: blind_backend
        end_product_type: interior_venetian_blind
        with_features:
          - lift
          - position_aware_lift
          - tilt
          - position_aware_tilt
```

Use snake_case names under `with_features`, matching the upstream endpoint
schema. The four features enable both position and tilt control. Setting only
the end product type does not enable tilt. The schema supplies the appropriate
Matter Window Covering type for each supported mapping. Cluster-level
`with_features` cannot add capabilities beyond the mapped cover's feature set.

## Native ESPHome API alongside Matter

To use Apple Home through Matter and Home Assistant through the ESPHome
integration, keep `api:` enabled and make the physical backend `internal: true`.
Expose a second cover using `platform: matter`:

```yaml
api:

cover:
  # Set internal: true in the existing blind_backend definition.
  - platform: matter
    id: blind_native
    name: Blind ESPHome
    device_class: blind
    cover_id: blind_backend
```

This platform comes from the `matter` external component; no additional
external `cover` component is needed. `cover_id` must reference an internal
backend mapped to exactly one Matter Window Covering endpoint. Each physical
backend can be mapped only once, and a native proxy cannot be an endpoint backend. The native
entity's name must differ from the backend's name so web requests select the
coordinated entity. `matter_id` may identify the parent Matter component;
ESPHome resolves it automatically when omitted.

The native entity mirrors the backend's position, tilt, and opening/closing
state. Native commands and Matter commands use the same queue. Native Stop
also cancels a tilt waiting behind a Matter lift command. State synchronization
does not restore movement targets on boot. Native control remains available if
Matter initialization fails, provided the backend itself is operational.

Home Assistant does not need Matter commissioning to use this native entity.
With a tilt-capable backend it supports the normal ESPHome tilt services,
including `cover.open_cover_tilt` and `cover.close_cover_tilt`. In the tested
Home Assistant Core 2026.9.4 Matter integration, tilt was controllable by a
slider but separate tilt-open/tilt-close controls were absent. That limitation
did not affect the native ESPHome entity.

## Lift, tilt, and Stop ordering

For a single-motor Venetian blind, lift and tilt run sequentially. When both
targets are requested, the coordinator completes lift before applying tilt.
A tilt request received during lift waits for lift to become idle. Further
tilt requests replace the waiting target with the newest value.

Stop cancels movement requests and continuations accepted before it. A new
movement sent after Stop may run normally. Local automations using the native
entity can call `cover.open`, `cover.close`, `cover.control`, and `cover.stop`
on that entity to use the same coordinator.

Automations that stop the backend directly must cancel pending work first:

```yaml
on_release:
  - matter.cover.cancel_pending:
      cover_id: blind_backend
  - cover.stop: blind_backend
```

Apply this ordering to every direct backend Stop path, including both physical
button releases and any Stop scripts. The cancellation action alone does not
stop the motor. A raw backend Stop at the lift destination can otherwise look
like normal completion and allow a waiting tilt to start.

## Position reporting

ESPHome and Matter use opposite position conventions:

| Target | ESPHome normalized value | Matter `Percent100ths` |
|---|---|---|
| Open | `1.0` | `0` |
| Halfway | `0.5` | `5000` |
| Closed | `0.0` | `10000` |

The same conversion applies to tilt. Check the backend's physical slat
orientation during calibration.

Backend publications update Matter current-position attributes and the native
entity during motion. The tested Venetian backend publishes progress about
once per second; its positions are estimates based on travel time. Reporting
frequency and accuracy depend on the backend.

During the canary test, Home Assistant displayed current positions while the
blind moved. Apple Home displayed opening/closing in its overview, but its
detail slider immediately showed the requested destination and stayed there
until the movement finished. Publishing current Matter positions does not
guarantee that every controller animates its slider.

## Hardware evidence and remaining checks

On 2026-10-01, the user confirmed lift, tilt, and Stop on a Shelly 2PM Gen4
(ESP32-C6) with Apple Home through Matter and Home Assistant through the native
ESPHome API, after switching from Wi-Fi to Thread. The tested firmware used
ESPHome 2026.8.2, ESP-IDF 5.5.5, and `davidvtwout/esp_matter` 1.6.0~2.

The current revision adds schema and coordinator fixes after that canary. Those
changes require a fresh hardware check before its earlier results can be applied
to this revision. A subsequent ESPHome 2026.9.0 Dashboard build had one
unexplained abort; its cause has not been identified.

The canary had no wired wall buttons. Physical button interruption and the
remaining retargeting checks still need hardware evidence. See the
[backend contract and test sequence](venetian-blind-backend-contract.md) for
the backend details and the next checks.
