# OTO for Home Assistant

An unofficial native Home Assistant integration for OTO smart sprinklers. It
connects directly to OTO's cloud—Homebridge is not required.

> [!WARNING]
> OTO does not publish or support this API. The integration may stop working
> if OTO changes its private cloud services. This project is not affiliated
> with or endorsed by OTO Lawn.

## What it provides

For each OTO controller:

- A truthful **Watering** binary sensor. OTO exposes activity at the controller
  level, not the active zone.
- A **Depth** number for every configured zone (1–50 mm).
- A stateless **Water** button for every zone.

There is deliberately no zone switch or valve. OTO cannot report which zone is
currently active, so such an entity would show fabricated state. There is also
no Stop button: the only discovered cloud operation merely regenerates the
schedule and is not a reliable immediate stop.

## Security and safety

- Your OTO password is used once during login and is **not stored**. Home
  Assistant stores the resulting Firebase refresh token in its protected
  config-entry storage.
- Diagnostics redact account, controller, zone, schedule, and location-like
  identifiers.
- Commands are serialized per controller, reject starts while watering, and
  include a duplicate-command cooldown.
- A timed-out start is never retried automatically because the first request
  may already have reached OTO.
- The initial depth is a conservative 1 mm. Review each zone's Depth entity
  before pressing Water.

## Installation

### HACS custom repository

1. In HACS, open **Integrations** → menu → **Custom repositories**.
2. Add `https://github.com/TristanBrotherton/home-assistant-oto` as an
   Integration repository.
3. Install **OTO**, restart Home Assistant, then go to
   **Settings → Devices & services → Add integration → OTO**.

### Manual

Copy `custom_components/oto` into Home Assistant's `custom_components`
directory, restart Home Assistant, and add the OTO integration from the UI.

## Configuration

Enter the email address and password used by the OTO app. The integration
validates the account and discovers controllers and zones. Use **Configure** on
the integration to change the polling interval and the default depth used for
newly discovered zones.

Each zone has its own Depth entity. Set it deliberately, then press the zone's
Water button. Home Assistant will reject another start if the controller is
already watering.

## Known limitations

- Cloud polling only; there is no supported local API on stock OTO firmware.
- OTO reports only controller-level activity, not the active zone.
- No reliable immediate-stop endpoint has been discovered.
- New controllers/zones require an integration reload in this initial release.
- Because the API is undocumented, response changes may require an update.

## Removal

Remove the integration from **Settings → Devices & services** and uninstall it
from HACS (or delete `custom_components/oto`). Removing the integration does not
change OTO schedules or device firmware.

## Credits

The cloud protocol was independently ported to Python from protocol research in
[`jonnadul/homebridge-oto`](https://github.com/jonnadul/homebridge-oto), licensed
under Apache-2.0. See [NOTICE](NOTICE).

## License

Apache License 2.0.

