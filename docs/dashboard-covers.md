# Covers in ESPHome Dashboard

The [Shelly 2PM Gen4 example](../examples/shelly-2pm-gen4-venetian-blind.yaml)
adds Matter and native ESPHome control to an existing, calibrated Venetian blind.
Dashboard downloads both external components from Git. The example needs your
local hardware package for GPIOs, relay protection, networking, OTA, and `cover1`.

## Prepare the hardware package

Copy your working base to `common/shelly_2pm_gen4_matter_base.yaml` in the
Dashboard configuration directory. Keep its pins, protection, calibration,
network settings, and child-lock conditions. The copy lets you update one device
before changing the shared base.

Move the `matter` and `venetian_blinds` external-component sources out of the
copied base; the device example supplies them. Keep any unrelated sources.

In both physical button release handlers, cancel pending Matter commands before
stopping the backend:

```yaml
on_release:
  - matter.cover.cancel_pending:
      cover_id: cover1
  - cover.stop: cover1
```

Update any other script that stops `cover1` directly in the same way. Edit the
existing handlers in the base: adding an `on_release` through `!extend` appends
an automation and will not put cancellation before the existing Stop. The
cancellation action requires Matter, so use this base with the Matter device YAML.

## Add the device YAML

Copy the [example](../examples/shelly-2pm-gen4-venetian-blind.yaml) into Dashboard.
Set the existing device name, cover name, child-lock helper, and measured travel
times. Adapt `cover1` if your backend has a different ID.

The example extends the package's `esp32` settings with `toolchain: platformio`
and marks `cover1` internal. The `cover1_api` entity provides native ESPHome
control through the same command handling as Matter. See [covers](covers.md)
for the endpoint and native cover options.

Both Git sources are pinned to specific commits. The Matter source uses this
fork while the cover changes await upstream review. To update it, replace its
`ref` with the commit you want to build. The `matter` component includes the
cover and text sensor platforms; no separate external components are needed.

Use **Validate**, then **Install**. The example limits compilation to one job
to reduce RAM use. **Clean Build Files** clears compiled output; it does not
update a pinned Git revision. See ESPHome's
[external component](https://esphome.io/components/external_components/) and
[package](https://esphome.io/components/packages/) documentation for details.

## Connect the controllers

Use Home Assistant's ESPHome integration for the `${cover1_name} ESPHome` entity.
The `Matter Setup Code` diagnostic entity supplies the code for initial Matter
commissioning. See [commissioning](commissioning.md) for adding a controller or
sharing an already commissioned device.

Start with a short movement and Stop, then check tilt and each wired button.
The package's child-lock conditions still apply only to the actions they guard;
they do not automatically block remote commands. See the
[hardware checks](dev/cover-testing.md#hardware-checks) for lift/tilt interruption
and retargeting checks.
