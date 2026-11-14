# Covers

Expose an existing ESPHome cover through a Matter `window_covering` endpoint:

```yaml
matter:
  endpoints:
    1:
      window_covering:
        cover_id: my_cover
        with_features:
          - position_aware_lift
```

Use the ID of a cover that reports position and supports Stop. For tilt control,
add `position_aware_tilt` and use a cover that supports tilt. The shared Matter
conformance resolver enables the corresponding `lift` and `tilt` features.
Tilt-only covers can use `position_aware_tilt` alone. Absolute physical positions
are unsupported because ESPHome covers expose normalized percentages.

`end_product_type` is optional: `roller_shade`, `interior_venetian_blind`, or
`exterior_venetian_blind`. The default is `roller_shade` for lift-only endpoints
and `interior_venetian_blind` when tilt is enabled.

Matter commands call the existing cover directly. The cover remains available
through ESPHome's native API, web server, and ordinary cover automations; it
does not need `internal: true` or a second control entity. Use normal
`cover.stop`, `cover.control`, and other ESPHome cover actions on its ID.
Motor timing, calibration, interlocking, and command interruption belong to
the cover implementation. A tilt command during lift follows that backend's
behavior; the Matter adapter does not wait for lift completion or queue tilt.

Backend state publications update Matter's current lift/tilt positions. ESPHome
exposes one movement operation: it is reported on lift when present, or tilt
for tilt-only covers, and Matter derives the overall status. Once the cover
reports idle, its actual positions also update the Matter targets. ESPHome does
not expose native command targets. When an API or local movement runs against
the Matter target's direction, the target is set to fully open or closed, so
controllers show the correct direction until the cover stops.
Initialization reports the existing state without moving the cover.

ESPHome uses `1.0` for open and `0.0` for closed. Matter uses `0` for open and
`10000` for closed. Both lift and tilt percentages are converted automatically;
verify the physical slat orientation for the selected backend.

If commands stop working after a firmware update that changed the cover's
features, the controller may have cached the old accessory model. Remove the
accessory and pair it again. The `matter.factory_reset` action clears all
Matter pairings; it preserves the ESPHome configuration and cover calibration.

See the [Wi-Fi test configuration](../tests/configs/esp32-window-covering.yaml)
for a complete example using a simulated cover, or the
[Thread configuration](../tests/configs/esp32-thread-window-covering.yaml).
