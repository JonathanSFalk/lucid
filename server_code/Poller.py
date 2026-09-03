import asyncio
import datetime

import anvil.secrets
import anvil.server
from anvil.tables import app_tables

from lucidmotors import LucidAPI, ChargeState
from lucidmotors.const import Region


async def _poll_once():
    """Log in, pull one fresh vehicle-state snapshot, and store it.

    auto_wake is left at its default (False): we only want to read
    whatever data Lucid's backend already has cached, not force the
    car to wake up on every poll.
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

        app_tables.readings.add_row(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            last_updated_ms=state.last_updated_ms,
            odometer_km=chassis.odometer_km,
            kwhr=battery.kwhr,
            capacity_kwhr=battery.capacity_kwhr,
            charge_percent=battery.charge_percent,
            remaining_range=battery.remaining_range,
            charge_state=ChargeState.Name(charging.charge_state),
            vehicle_id=vehicle.vehicle_id,
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
