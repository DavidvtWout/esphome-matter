# Cover testing

For user configuration, see [covers](../covers.md) and the
[Dashboard guide](../dashboard-covers.md).

## Backend behavior

The adapter uses the ESPHome cover API. Motor timing, relay interlocking,
reversal delays, calibration, and protection remain the backend's responsibility.

The reference backend is `bruxy70/Venetian-Blinds-Control` at commit
`41abbe36877efa85db346913bf4b889aca72b643`. It estimates lift and tilt from travel
times, publishes progress about once per second, and publishes a final state
after completion or Stop. Lift and tilt share one motor: lift rotates the slats
before changing height, while tilt alone preserves the lift estimate.

In this backend, a `CoverCall` containing both targets lets tilt overwrite lift.
The adapter therefore sends lift first, waits for idle, then sends the latest
tilt target. ESPHome's state callback does not identify why movement stopped.
A local Stop at the requested lift position is indistinguishable from completion,
so direct backend Stop actions must explicitly cancel pending work first. See
[Stop handling](../covers.md#lift-tilt-and-stop).

## Automated coverage

The host tests compile the production queue and cover mapping against simulated
ESPHome and Matter interfaces. They cover command ordering, Stop cancellation,
asynchronous stopping, overshoot, retargeting, delayed state reports, scheduling
retry, and native cover control. Configuration tests cover validation and code
generation for Wi-Fi and Thread. CI also builds firmware against the real SDK.
These checks do not exercise a motor or controller subscriptions.

## Hardware results

An earlier revision passed lift, tilt, and Stop on a Shelly 2PM Gen4 (ESP32-C6)
with Apple Home through Matter and Home Assistant through the native ESPHome API.
Wi-Fi was checked on 2026-09-30 and Thread on 2026-10-01; switching networks
preserved the Matter fabrics. That build used ESPHome `2026.8.2`, ESP-IDF `5.5.5`,
`davidvtwout/esp_matter` `1.6.0~2`, and the backend revision above.

The subsequent schema and command-coordination fixes still need a hardware
check. The test device had no wired buttons, so physical button interruption
has not been verified. A later ESPHome `2026.9.0` Dashboard build also reported
an abort whose cause remains unknown.

## Hardware checks

Test with someone watching the blind. Record the firmware revision, backend
revision, controller versions, and results:

1. Check the reported lift and tilt positions before moving.
2. Make a small lift movement and Stop, then a small tilt movement and Stop.
3. Send several tilt targets during lift. Only the latest should run after lift
   finishes.
4. Repeat with Stop from Matter, the native ESPHome entity, and every wired
   button or Stop script. Include Stop near lift completion; the waiting tilt
   must not start afterward.
5. Retarget lift to the current position during movement. The previous
   destination must be canceled.
6. After local movement, Stop, and completion, compare the physical position and
   ESPHome state with Matter's current/target position and `OperationalStatus`
   attributes. Check tilt orientation as well as its reported percentage.
7. Reboot and confirm both controllers reconnect. For Thread discovery problems,
   see [Thread debugging](thread-debugging.md#commissioned-devices-after-reboot).
