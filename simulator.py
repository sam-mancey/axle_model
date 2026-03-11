"""
simulator.py
------------
Core simulation engine for EV driver behaviour.

Two public functions:
- build_agents()     — creates a list of EVDriver agents from archetypes
- run_simulation()   — runs the simulation and returns two DataFrames:
                       1. plug_events_df  — one row per plug event (daily resolution)
                       2. halfhourly_df   — half-hourly grid of % plugged in + mean SoC

Design decisions:
- Plug events span midnight as single continuous events with full datetimes
- Plug-out SoC is derived from charger_kw × charging_hrs / battery_kwh
- Charger stops at target_soc; plugin_soc >= target_soc → plug event recorded, zero charge
- Constant charge rate throughout (no taper above 80% SoC)
- Noise is re-sampled each day per agent (realistic variation) with optional fixed seed
- Agent archetypes are weighted by population_pct by default; overridable via weights dict
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass
from archetypes import ARCHETYPES
from config import SIMULATION_DEFAULTS


# ---------------------------------------------------------------------------
# EVDriver agent
# ---------------------------------------------------------------------------

@dataclass
class EVDriver:
    """
    Represents a single EV driver agent.

    Parameters are fixed at creation (archetype assignment, battery size etc).
    Day-to-day variation in plug-in time and SoC is re-sampled each day using
    the archetype's std_dev parameters and the simulation's random state.
    """
    agent_id: str
    archetype: dict                  # full archetype parameter dict from archetypes.py

    def will_plug_in(self, rng: np.random.Generator) -> bool:
        """Bernoulli draw — did this agent plug in today?"""
        return rng.random() < self.archetype["plug_frequency"]

    def sample_plugin_time(
        self,
        rng: np.random.Generator,
        date: datetime,
        plugin_offset_hrs: float = 0.0,
    ) -> datetime:
        """
        Sample plug-in datetime for a given date.
        Applies Gaussian noise around archetype mean + any sidebar offset.
        """
        base_hr = self.archetype["plugin_time_hr"] + plugin_offset_hrs
        noise = rng.normal(0, self.archetype["std_dev_plugin_hrs"])
        plugin_hr = base_hr + noise
        return date + timedelta(hours=plugin_hr)

    def sample_plugout_time(
        self,
        rng: np.random.Generator,
        plugin_dt: datetime,
    ) -> datetime:
        """
        Sample plug-out datetime.
        Plug-out is on the next calendar day if plugout_time_hr < plugin_time_hr
        (i.e. overnight charging), otherwise same day.
        Always returns a datetime after plugin_dt.
        """
        noise = rng.normal(0, self.archetype["std_dev_plugout_hrs"])
        plugout_hr = self.archetype["plugout_time_hr"] + noise

        # Determine base date for plug-out
        plugin_hr = self.archetype["plugin_time_hr"]
        if plugout_hr < plugin_hr or self.archetype["plugout_time_hr"] >= 23.5:
            # Overnight — plug out the next morning
            base_date = plugin_dt.date() + timedelta(days=1)
        else:
            base_date = plugin_dt.date()

        plugout_dt = datetime.combine(base_date, datetime.min.time()) + timedelta(hours=plugout_hr)

        # Safety: ensure plugout is always after plugin
        if plugout_dt <= plugin_dt:
            plugout_dt = plugin_dt + timedelta(hours=1)

        return plugout_dt

    def sample_plugin_soc(self, rng: np.random.Generator) -> float:
        """Sample plug-in SoC with Gaussian noise, clamped to [0.05, 1.0]."""
        soc = rng.normal(
            self.archetype["plugin_soc_mean"],
            self.archetype["std_dev_soc"],
        )
        return float(np.clip(soc, 0.05, 1.0))

    def compute_plugout_soc(self, plugin_soc: float, plug_duration_hrs: float) -> tuple[float, float]:
        """
        Derive plug-out SoC from constant charge rate model.

        Returns (plugout_soc, kwh_delivered).
        If plugin_soc >= target_soc, no charge is delivered (habitual plug-in).
        Charge stops at target_soc.
        """
        target = self.archetype["target_soc"]
        battery = self.archetype["battery_kwh"]
        charger_kw = self.archetype["charger_kw"]

        if plugin_soc >= target:
            # Plugged in but no charge needed
            return plugin_soc, 0.0

        # How much SoC can we add in the available time?
        max_kwh = charger_kw * plug_duration_hrs
        max_soc_gain = max_kwh / battery
        soc_needed = target - plugin_soc

        actual_soc_gain = min(soc_needed, max_soc_gain)
        plugout_soc = float(np.clip(plugin_soc + actual_soc_gain, 0.0, 1.0))
        kwh_delivered = actual_soc_gain * battery

        return plugout_soc, kwh_delivered


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

def build_agents(
    n_agents: int,
    weights: dict | None = None,
    seed: int = SIMULATION_DEFAULTS["random_seed"],
) -> list[EVDriver]:
    """
    Build a list of EVDriver agents.

    By default, archetypes are assigned by weighted random sampling using
    population_pct from the CSV. Pass a weights dict keyed by archetype name
    to override (values are relative weights, normalised automatically).

    Args:
        n_agents: total number of agents to create
        weights:  optional dict of {archetype_name: weight} overrides
        seed:     random seed for reproducible agent assignment
    """
    rng = np.random.default_rng(seed)

    # Build weight array — use overrides if provided, else CSV population_pct
    names = [a["name"] for a in ARCHETYPES]
    if weights:
        raw_weights = [weights.get(name, a["population_pct"]) for name, a in zip(names, ARCHETYPES)]
    else:
        raw_weights = [a["population_pct"] for a in ARCHETYPES]

    # Normalise to sum to 1
    total = sum(raw_weights)
    norm_weights = [w / total for w in raw_weights]

    # Sample archetype indices
    archetype_indices = rng.choice(len(ARCHETYPES), size=n_agents, p=norm_weights)

    agents = [
        EVDriver(
            agent_id=f"agent_{i:04d}",
            archetype=ARCHETYPES[idx],
        )
        for i, idx in enumerate(archetype_indices)
    ]

    return agents


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------

def run_simulation(
    agents: list[EVDriver],
    n_days: int = SIMULATION_DEFAULTS["n_days"],
    seed: int = SIMULATION_DEFAULTS["random_seed"],
    start_date: datetime = datetime(2024, 1, 1),
    plugin_time_offsets: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the simulation over n_days for all agents.

    Args:
        agents:               list of EVDriver agents from build_agents()
        n_days:               number of days to simulate
        seed:                 random seed for reproducible day-level noise
        start_date:           simulation start date
        plugin_time_offsets:  optional dict of {archetype_name: offset_hrs}
                              from Streamlit sidebar sliders

    Returns:
        plug_events_df:  one row per plug event with full timestamps and SoC
        halfhourly_df:   half-hourly grid with % plugged in and mean SoC
    """
    rng = np.random.default_rng(seed)
    plugin_time_offsets = plugin_time_offsets or {}

    plug_events = []

    # Track last plug-out per agent to avoid overlapping events for
    # always-plugged-in archetype (plugout_time_hr >= 23.5 spans nearly 24hrs)
    last_plugout: dict = {}

    for day_idx in range(n_days):
        date = start_date + timedelta(days=day_idx)

        for agent in agents:
            if not agent.will_plug_in(rng):
                continue

            offset = plugin_time_offsets.get(agent.archetype["name"], 0.0)
            plugin_dt = agent.sample_plugin_time(rng, date, offset)

            # Skip if this agent is still plugged in from a previous event
            if agent.agent_id in last_plugout and plugin_dt < last_plugout[agent.agent_id]:
                continue

            plugout_dt = agent.sample_plugout_time(rng, plugin_dt)
            last_plugout[agent.agent_id] = plugout_dt
            plugin_soc = agent.sample_plugin_soc(rng)

            plug_duration_hrs = (plugout_dt - plugin_dt).total_seconds() / 3600
            plugout_soc, kwh_delivered = agent.compute_plugout_soc(plugin_soc, plug_duration_hrs)
            charging_hrs = kwh_delivered / agent.archetype["charger_kw"] if kwh_delivered > 0 else 0.0

            plug_events.append({
                "agent_id": agent.agent_id,
                "archetype": agent.archetype["name"],
                "plugin_dt": plugin_dt,
                "plugout_dt": plugout_dt,
                "plugin_soc": round(plugin_soc, 3),
                "plugout_soc": round(plugout_soc, 3),
                "kwh_delivered": round(kwh_delivered, 2),
                "charging_hrs": round(charging_hrs, 2),
                "plug_duration_hrs": round(plug_duration_hrs, 2),
                "charger_kw": agent.archetype["charger_kw"],
            })

    plug_events_df = pd.DataFrame(plug_events)

    # Build half-hourly grid
    halfhourly_df = _build_halfhourly_grid(plug_events_df, start_date, n_days, len(agents))

    return plug_events_df, halfhourly_df


# ---------------------------------------------------------------------------
# Half-hourly grid builder
# ---------------------------------------------------------------------------

def _kwh_this_slot(row: pd.Series, slot: datetime) -> float:
    """
    Calculate kWh drawn by a single charging event during a given half-hour slot.
    Uses remaining kWh at slot start to handle the partial final charging slot
    correctly — avoids over-attributing demand in the last 30-min window.
    """
    if row["charging_hrs"] <= 0:
        return 0.0
    elapsed = (slot - row["plugin_dt"]).total_seconds() / 3600
    remaining_kwh = row["kwh_delivered"] - (elapsed * row["charger_kw"] if elapsed > 0 else 0)
    return min(row["charger_kw"] * 0.5, max(0.0, remaining_kwh))


def _build_halfhourly_grid(
    plug_events_df: pd.DataFrame,
    start_date: datetime,
    n_days: int,
    n_agents: int,
) -> pd.DataFrame:
    """
    Build a half-hourly time series of:
    - pct_plugged_in:    fraction of all agents plugged in during each slot
    - mean_plugin_soc:   mean SoC of plugged-in agents at plug-in
    - total_kwh_demand:  total kWh actively drawn during each slot

    An agent is plugged in if plugin_dt <= slot < plugout_dt.
    An agent is charging if plugin_dt <= slot < charging_end_dt.
    After charging_end_dt the car is idle — plugged in but drawing zero power.
    """
    if plug_events_df.empty:
        return pd.DataFrame()

    end_date = start_date + timedelta(days=n_days)
    slots = pd.date_range(start=start_date, end=end_date, freq="30min", inclusive="left")

    # Pre-compute charging_end_dt — when the car stops drawing power.
    # After this point it is plugged in but idle.
    plug_events_df = plug_events_df.copy()
    plug_events_df["charging_end_dt"] = (
        plug_events_df["plugin_dt"] +
        pd.to_timedelta(plug_events_df["charging_hrs"], unit="h")
    )

    records = []
    for slot in slots:
        # Agents plugged in this slot (connected but not necessarily charging)
        plugged_mask = (
            (plug_events_df["plugin_dt"] <= slot) &
            (plug_events_df["plugout_dt"] > slot)
        )
        plugged = plug_events_df[plugged_mask]
        n_plugged = len(plugged)

        # Agents actively charging this slot
        charging_mask = plugged_mask & (plug_events_df["charging_end_dt"] > slot)
        charging = plug_events_df[charging_mask]

        slot_kwh = charging.apply(_kwh_this_slot, axis=1, slot=slot).sum() if len(charging) > 0 else 0.0

        records.append({
            "slot": slot,
            "hour_of_day": slot.hour + slot.minute / 60,
            "day_of_week": slot.day_name(),
            "n_plugged": n_plugged,
            "pct_plugged_in": n_plugged / n_agents if n_agents > 0 else 0.0,
            "mean_plugin_soc": plugged["plugin_soc"].mean() if n_plugged > 0 else None,
            "total_kwh_demand": round(slot_kwh, 3),
        })

    return pd.DataFrame(records)