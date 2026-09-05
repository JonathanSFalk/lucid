from ._anvil_designer import Form1Template
from anvil import *
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server


class Form1(Form1Template):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._populate_efficiency_plot()
    self._populate_timeline_plot()

  def _populate_efficiency_plot(self):
    """plot_1: actual vs. dash-predicted Wh/km, one point per hourly
    driving leg (see Dashboard.get_driving_legs - no trip-level grouping,
    so the real efficiency swings within a drive stay visible).

    x is a *category* axis of formatted leg-start labels, not a real
    time axis - legs are often hours or days apart (charging/parked time
    in between), and a linear/date x-axis would stretch the plot out
    with a long flat gap for every such interval. Category spacing keeps
    every leg evenly spaced regardless of the real-world gap before it."""
    legs = anvil.server.call('get_driving_legs')
    # Drop legs where the dash gave no prediction (remaining_range was
    # 0/missing at the leg's start) - otherwise a lone "Actual" point
    # shows up with no "Dash's predicted" counterpart to compare it to.
    legs = [leg for leg in legs if leg['predicted_wh_per_km'] is not None]
    x = [self._format_leg_label(leg['start']) for leg in legs]

    self.plot_1.data = [
      {
        'type': 'scatter',
        'mode': 'lines+markers',
        'name': 'Actual (Wh/km)',
        'x': x,
        'y': [leg['actual_wh_per_km'] for leg in legs],
      },
      {
        'type': 'scatter',
        'mode': 'lines+markers',
        'name': "Dash's predicted (Wh/km)",
        'x': x,
        'y': [leg['predicted_wh_per_km'] for leg in legs],
      },
    ]
    self.plot_1.layout = {
      'xaxis': {'title': 'Leg start (local time)', 'type': 'category'},
      'yaxis': {'title': 'Wh/km'},
      'legend': {'orientation': 'h', 'y': -0.2},
      'margin': {'t': 20},
    }

  @staticmethod
  def _format_leg_label(dt):
    """Succinct fixed-width label for a category-axis tick, e.g. '9/3 18:00'."""
    return '%d/%d %02d:%02d' % (dt.month, dt.day, dt.hour, dt.minute)

  def _populate_timeline_plot(self):
    """plot_2: every stored reading, unfiltered - raw battery/range/charge
    timeline (see Dashboard.get_timeline). Range-line markers are colored
    by charge_state so charging periods stand out."""
    rows = anvil.server.call('get_timeline')
    x = [r['timestamp'] for r in rows]
    charging = [r['charge_state'] != 'CHARGE_STATE_NOT_CONNECTED' for r in rows]
    point_colors = ['#e07b39' if c else '#1f77b4' for c in charging]

    self.plot_2.data = [
      {
        'type': 'scatter',
        'mode': 'lines+markers',
        'name': 'Remaining Range (km)',
        'x': x,
        'y': [r['remaining_range'] for r in rows],
        'marker': {'color': point_colors},
      },
      {
        'type': 'scatter',
        'mode': 'lines',
        'name': 'Battery (kWh)',
        'x': x,
        'y': [r['kwhr'] for r in rows],
        'line': {'dash': 'dot'},
      },
      {
        'type': 'scatter',
        'mode': 'lines',
        'name': 'Charge %',
        'x': x,
        'y': [r['charge_percent'] for r in rows],
        'yaxis': 'y2',
        'line': {'color': '#2ca02c'},
      },
    ]
    self.plot_2.layout = {
      'xaxis': {'title': 'Time (local)'},
      'yaxis': {'title': 'Range (km) / Battery (kWh)'},
      'yaxis2': {
        'title': 'Charge %',
        'overlaying': 'y',
        'side': 'right',
        'range': [0, 100],
      },
      'legend': {'orientation': 'h', 'y': -0.2},
      'margin': {'t': 20},
    }
