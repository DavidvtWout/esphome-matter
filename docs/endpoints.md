Each endpoint is defined by its ID which can range from 0 to 65534. An endpoint at id 0 with device type `Root Node` is always created. This device type defines clusters such as `AccessControl`, `BasicInformation`, diagnostic clusters and clusters that are used for commissioning.

Beneath an endpoint are clusters. Clusters are collections of attributes and commands with more or less a single function. For example the `OnOff` cluster defines attributes such as the state, startup behaviour and defines commands such as `on`, `off` and `toggle`.

# Device types

To make cluster management more convenient, Matter defines device types. For example, the `Dimmable Light` creates clusters such as `OnOff` and `LevelControl`. Different device types may define the same clusters, so if you're not sure, it's best to assign only a single device type to each endpoint.

For all supported device types, see the documentation on [device types](device-types.md).

# ESPHome cover mapping

An existing ESPHome cover can be attached to a Matter Window Covering endpoint
with `cover_id`. Mapped covers currently support normalized percentage
positions in one of two feature combinations:

- Lift only: `Lift` and `PositionAwareLift`
- Venetian blind: `Lift`, `PositionAwareLift`, `Tilt`, and
  `PositionAwareTilt`

`AbsolutePosition` is not supported because ESPHome cover positions are
normalized percentages rather than physical measurements.

```yaml
matter:
  endpoints:
    1:
      window_covering:
        cover_id: venetian_blind
        end_product_type: interior_venetian_blind
        features:
          - Lift
          - PositionAwareLift
          - Tilt
          - PositionAwareTilt
```

The mapped cover must report position and support Stop. A Venetian-blind
mapping must also report tilt. Runtime capability checks are part of the cover
mapping implementation.

For lift-only mappings, `end_product_type` defaults to `roller_shade`. For
lift-and-tilt mappings it defaults to `interior_venetian_blind`;
`exterior_venetian_blind` is also accepted. These end product types describe the
cover; tilt support still requires all four features listed above.

The Matter adapter converts Matter's `0 = open`, `10000 = closed` percentages
to ESPHome's normalized `1.0 = open`, `0.0 = closed` convention. For a
single-motor Venetian backend it performs lift first and the final tilt second.
See [Venetian blind backend contract](venetian-blind-backend-contract.md) for
the tested backend semantics and safety boundaries.

To expose the same backend through the native ESPHome API, set it
`internal: true` and add a separate `cover: platform: matter` entity referencing
that backend. Give the native entity a different name and map its backend to
exactly one Window Covering endpoint. Direct backend Stop automations must
call `matter.cover.cancel_pending` before `cover.stop`.

See [covers](covers.md) for both feature combinations, the native entity,
command ordering, and current-position reporting, or the
[Dashboard guide](dashboard-covers.md) to load the component from Git.
