import asyncio
import datetime

import anvil.secrets
import anvil.server
import anvil.tables as tables
from anvil.tables import app_tables

from lucidmotors import LucidAPI, ChargeState
from lucidmotors.const import Region

# Below this, a kwhr delta is treated as cache noise rather than a real
# change. Parasitic drain while parked shows up as roughly 0.01-0.05 kWh
# per hour, so this stays well under a real reading while still catching
# any float jitter Lucid's backend might introduce.
KWHR_NOISE_FLOOR = 0.01


async def _poll_once():
    """Log in, pull one fresh vehicle-state snapshot, and store it.

    Lucid's backend routinely serves back literally the same cached values
    on consecutive polls - last_updated_ms keeps advancing even when
    nothing changed, so it's not a reliable "did anything happen" signal.
    Instead we compare the fields that actually matter: if the odometer
    and charge state haven't moved and the battery level has drifted by
    less than KWHR_NOISE_FLOOR, treat this as the same underlying reading
    as last time. In that case we just refresh the existing row's
    timestamp and last_updated_ms (keeping it current rather than frozen,
    so the *next* real change can compute an accurate elapsed-time delta)
    and bump poll_count. Otherwise we insert a fresh row - including
    small but real parasitic-drain-only changes, which are useful signal,
    not noise to be discarded.

    auto_wake is left at its default (False): we only want to read
    whatever data Lucid's backend already has cached, not force the car
    to wake up on every poll.
    """
    async with LucidAPI(region=Region.US) as api:
        await api.login(
            anvil.secrets.get_secret('User'),
            anvil.secrets.get_secret('Password'),
        )
        vehicles = await api.fetch_vehicles()
        vehicle = vehicles[0]
        state = vehicle.state
        battery = state.battery
        chassis = state.chassis
        charging = state.charging

        now = datetime.datetime.now(datetime.timezone.utc)
        charge_state = ChargeState.Name(charging.charge_state)

        latest = next(
            iter(app_tables.readings.search(
                tables.order_by("timestamp", ascending=False)
            )),
            None,
        )

        if (
            latest is not None
            and latest['odometer_km'] == chassis.odometer_km
            and latest['charge_state'] == charge_state
            and abs(latest['kwhr'] - battery.kwhr) < KWHR_NOISE_FLOOR
        ):
            # Same underlying reading as last time - just record that we
            # checked. last_updated_ms/timestamp get refreshed (not left
            # frozen at the first occurrence) so that whenever the next
            # real change shows up, the elapsed-time delta is measured
            # from the most recent confirmed-unchanged poll, not from
            # however far back this run of duplicates started.
            latest.update(
                timestamp=now,
                last_updated_ms=state.last_updated_ms,
                poll_count=(latest['poll_count'] or 1) + 1,
            )
            return

        app_tables.readings.add_row(
            timestamp=now,
            last_updated_ms=state.last_updated_ms,
            odometer_km=chassis.odometer_km,
            kwhr=battery.kwhr,
            capacity_kwhr=battery.capacity_kwhr,
            charge_percent=battery.charge_percent,
            remaining_range=battery.remaining_range,
            charge_state=charge_state,
            vehicle_id=vehicle.vehicle_id,
            poll_count=1,
        )


@anvil.server.background_task
def poll_vehicle():
    """The actual poller. Runs only from the Scheduled Task, or from
    manual_poll() below via launch_background_task - it has no
    client-callable path of its own, so it needs no caller check."""
    asyncio.run(_poll_once())


@anvil.server.callable
def manual_poll(admin_key):
    """Client-triggerable rerun. Gated on a shared secret (not the Lucid
    login) so the public app URL can't be used by a stranger to trigger
    polls, spend our Lucid API quota, or see anything back."""
    if admin_key != anvil.secrets.get_secret('AdminKey'):
        raise anvil.server.PermissionDenied("Invalid admin key")
    return anvil.server.launch_background_task('poll_vehicle')
