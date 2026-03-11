"""
config.py
---------
Central assumptions and defaults for the EV driver behaviour simulator.

Two categories of settings:
1. SIMULATION_DEFAULTS — default values for parameters exposed in the
   Streamlit sidebar. These are the starting values; the user can override
   them live during a session.

2. STD_DEV_ASSUMPTIONS — Gaussian noise parameters controlling
   within-archetype variation. Edit these to explore sensitivity to
   different behavioural assumptions without touching simulation logic.

Charging model assumptions (not currently in sidebar):
- Constant charge rate at charger_kw throughout (no taper above 80% SoC)
- Charger stops at target_soc; if plugin_soc >= target_soc, no charge delivered
- Plug events span midnight as single continuous events (not split at day boundary)

NOTE: archetype name keys must match exactly the 'name' column in driver_types.csv.
"""

# ---------------------------------------------------------------------------
# Simulation defaults — starting values for the Streamlit sidebar
# ---------------------------------------------------------------------------
SIMULATION_DEFAULTS = {
    "n_agents": 200,
    "n_days": 30,
    "random_seed": 42,
}

# ---------------------------------------------------------------------------
# Per-archetype plug-in time offsets (hours) — sidebar slider defaults
# Additive offset on top of the archetype's base plugin_time_hr.
# e.g. 0.0 = no adjustment; +1.0 = plug in one hour later on average.
# ---------------------------------------------------------------------------
PLUGIN_TIME_OFFSETS = {
    "Average (UK)": 0.0,
    "Intelligent Octopus average": 0.0,
    "Infrequent charging": 0.0,
    "Infrequent driving": 0.0,
    "Scheduled charging": 0.0,
    "Always plugged-in": 0.0,
}

# ---------------------------------------------------------------------------
# Per-archetype population weight overrides — sidebar slider defaults
# Values are relative weights, normalised to sum to 1.0 at runtime.
# ---------------------------------------------------------------------------
POPULATION_WEIGHT_OVERRIDES = {
    "Average (UK)": 0.40,
    "Intelligent Octopus average": 0.30,
    "Infrequent charging": 0.10,
    "Infrequent driving": 0.10,
    "Scheduled charging": 0.09,
    "Always plugged-in": 0.01,
}

# ---------------------------------------------------------------------------
# Gaussian noise assumptions — edit to explore behavioural sensitivity
# ---------------------------------------------------------------------------
STD_DEV_ASSUMPTIONS = {
    "Always plugged-in": {
        "plugin_hrs": 0.1,
        "plugout_hrs": 0.1,
        "soc": 0.03,
    },
    "Scheduled charging": {
        "plugin_hrs": 0.5,
        "plugout_hrs": 0.5,
        "soc": 0.05,
    },
    "Infrequent charging": {
        "plugin_hrs": 1.5,
        "plugout_hrs": 1.0,
        "soc": 0.10,
    },
    "default": {
        "plugin_hrs": 0.75,
        "plugout_hrs": 0.5,
        "soc": None,  # dynamically derived from plug-in SoC — see archetypes._derive_std_devs()
    },
}