import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server
from datetime import timezone
from zoneinfo import ZoneInfo

# The car only ever operates around Rye, NY and Williamstown, MA - both
# America/New_York - so we convert stored UTC timestamps to that zone for
# display rather than deriving a timezone from GPS. Revisit if the car's
# usage pattern ever changes (e.g. a long trip outside the Eastern zone).
EASTERN = ZoneInfo("America/New_York")

NOT_CONNECTED = "CHARGE_STATE_NOT_CONNECTED"


def _to_local(dt):
    """Stored timestamps are UTC (see Poller.py) - convert for display."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN)


@anvil.server.callable
def get_driving_legs():
    """One entry per hourly interval where the car was parked-or-driving
    (never charging) on both ends of the interval and the odometer moved -
    i.e. a real driving leg, left at native hourly resolution (no
    trip-level grouping - the ~2x efficiency swing seen within a single
    drive is real signal, not something to smooth away).

    Compares actual Wh/km consumed during the leg against what the dash's
    own remaining_range/kwhr implied *at the start* of the leg - that's
    the dash's forward-looking prediction being tested.

    Any interval touching a charging state is skipped entirely (a leg's
    kwhr delta only means "energy used for driving" when nothing was
    added back via charging during that same interval).
    """
    rows = list(app_tables.readings.search(tables.order_by("timestamp")))
    legs = []
    for prev, curr in zip(rows, rows[1:]):
        if prev['charge_state'] != NOT_CONNECTED or curr['charge_state'] != NOT_CONNECTED:
            continue
        distance_km = curr['odometer_km'] - prev['odometer_km']
        if distance_km <= 0:
            continue
        energy_kwh = prev['kwhr'] - curr['kwhr']
        actual_wh_per_km = energy_kwh * 1000 / distance_km
        predicted_wh_per_km = (
            prev['kwhr'] * 1000 / prev['remaining_range']
            if prev['remaining_range'] else None
        )
        delta_pct = (
            100 * (actual_wh_per_km - predicted_wh_per_km) / predicted_wh_per_km
            if predicted_wh_per_km else None
        )
        legs.append({
            'start': _to_local(prev['timestamp']),
            'end': _to_local(curr['timestamp']),
            'distance_km': distance_km,
            'energy_kwh': energy_kwh,
            'actual_wh_per_km': actual_wh_per_km,
            'predicted_wh_per_km': predicted_wh_per_km,
            'delta_pct': delta_pct,
        })
    return legs


@anvil.server.callable
def get_timeline():
    """Every stored reading, in order, for the raw battery/range timeline
    view - no filtering, no aggregation, no leg detection."""
    rows = list(app_tables.readings.search(tables.order_by("timestamp")))
    return [{
        'timestamp': _to_local(r['timestamp']),
        'charge_percent': r['charge_percent'],
        'kwhr': r['kwhr'],
        'remaining_range': r['remaining_range'],
        'charge_state': r['charge_state'],
        'odometer_km': r['odometer_km'],
    } for r in rows]
