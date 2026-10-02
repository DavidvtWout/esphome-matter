# Covers

The `window_covering` device type exposes an existing ESPHome cover to Matter.
It supports lift position, Stop, and optional tilt control for Venetian blinds.
The existing cover (the backend) still handles motor control, calibration,
relay interlocking, and protection.

## Configuration

The backend must report position and support Stop. Use its ID as `cover_id`:

```yaml
matter:
  endpoints:
    1:
      window_covering:
        cover_id: blind_backend
        with_features:
          - lift
          - position_aware_lift
```

For a Venetian blind, the backend must also support tilt. Replace `with_features`
under `window_covering` with all four features:

```yaml
with_features:
  - lift
  - position_aware_lift
  - tilt
  - position_aware_tilt
```

### Configuration variables

- **cover_id** (**Required**, ID): The existing ESPHome cover to expose. Each
  backend can be mapped to one endpoint.
- **with_features** (**Required**, list): One of the two combinations above.
  Absolute positions and tilt-only mappings are not supported.
- **end_product_type** (*Optional*, string): Describes the cover to Matter
  controllers. Defaults to `roller_shade` for lift only, or
  `interior_venetian_blind` for lift and tilt. A lift-and-tilt cover can also use
  `exterior_venetian_blind`. This option does not enable tilt by itself.

For an existing Shelly 2PM Gen4 configuration, see the
[Dashboard guide](dashboard-covers.md) and
[device example](../examples/shelly-2pm-gen4-venetian-blind.yaml).

## Native ESPHome control

To use Matter and native ESPHome control together, enable the
[API](https://esphome.io/components/api/), set `internal: true` on the backend,
and add a `matter` cover:

```yaml
cover:
  - platform: matter
    name: Blind ESPHome
    cover_id: blind_backend
```

The backend is hidden from Home Assistant; the new entity exposes its position,
tilt, and movement state. Both Matter and native commands then use the same
lift/tilt ordering and Stop handling. Home Assistant can use this entity through
its ESPHome integration without joining a Matter fabric, including the normal
tilt-open and tilt-close services.

### Configuration variables

- **cover_id** (**Required**, ID): The internal backend mapped to the Matter
  endpoint above. Keep the endpoint mapped to the backend, not this new entity.
- **matter_id** (*Optional*, ID): The Matter component. Automatically resolved
  when omitted.
- All other options from [Cover](https://esphome.io/components/cover/).
  Give the new entity a different name from the backend so web requests can
  distinguish them.

This platform is included in the `matter` external component. Native control
also works if Matter initialization fails, provided the backend is operational.

## Lift, tilt, and Stop

Lift and tilt run sequentially. A tilt requested during lift waits until lift
finishes; further tilt requests replace the waiting target. Stop cancels the
movement and any waiting tilt. A new movement requested after Stop can run.

Automations can use the normal ESPHome cover actions on the native entity.
If an automation stops the backend directly, cancel pending commands first:

```yaml
on_release:
  - matter.cover.cancel_pending:
      cover_id: blind_backend
  - cover.stop: blind_backend
```

Use this order in every direct backend Stop path, including both button release
handlers and Stop scripts. The cancellation action alone does not stop the
motor. Without it, a Stop at the lift destination can look like normal completion
and allow a waiting tilt to start. Stopping the native entity already handles
this cancellation.

## Position reporting

Current positions update whenever the backend publishes state. Their accuracy
and update frequency depend on the backend; time-based covers estimate position
from the configured travel times.

ESPHome uses `1.0` for open and `0.0` for closed. Matter's `Percent100ths`
attributes use `0` for open and `10000` for closed. The component converts both
lift and tilt values automatically. Check the physical slat orientation when
calibrating tilt.

Controller apps may display the target while the blind moves. Apple Home's
detail slider has shown this behavior even when current-position reports were
updating correctly. For development and hardware checks, see
[cover testing](dev/cover-testing.md).
