"""
archetypes.py
-------------
Loads EV driver archetypes from driver_types.csv and parses them into
a clean list of dicts for use by simulator.py.

Gaussian noise parameters (std_dev_*) are not in the CSV — they are read
from config.STD_DEV_ASSUMPTIONS. Edit that file to change assumptions
without touching simulation logic.

Assumptions:
- plugin_time_hr and plugout_time_hr are in decimal hours (e.g. 18.0 = 6:00 PM)
- plugin_soc_mean and target_soc are stored as floats between 0 and 1
- plug_frequency is a daily probability (e.g. 0.2 = plugs in ~once every 5 days)
- CSV lives at the repo root alongside this file
"""

import pandas as pd
from pathlib import Path
from config import STD_DEV_ASSUMPTIONS

CSV_PATH = Path(__file__).parent / "driver_types.csv"


def _parse_time_to_decimal(time_str: str) -> float:
    """Convert '6:00 PM' or '10:00 PM' style strings to decimal hours."""
    t = pd.to_datetime(time_str, format="%I:%M %p")
    return t.hour + t.minute / 60


def _parse_pct(pct_str) -> float:
    """Convert '80%' or '68%' to 0.80, 0.68 etc."""
    if isinstance(pct_str, str):
        return float(pct_str.strip("%")) / 100
    return float(pct_str) / 100


def _derive_std_devs(row: dict) -> dict:
    """
    Append Gaussian noise parameters based on archetype behaviour.
    Values are read from config.STD_DEV_ASSUMPTIONS — edit that file
    to explore sensitivity to different assumptions without touching this logic.
    """
    name = row["name"]
    assumptions = STD_DEV_ASSUMPTIONS.get(name, STD_DEV_ASSUMPTIONS["default"])

    # soc std dev: use config value if explicitly set, otherwise derive
    # dynamically from how much charge this archetype typically uses per session
    if assumptions["soc"] is not None:
        soc_std = assumptions["soc"]
    else:
        soc_usage = row["plugin_soc_mean"]
        soc_std = round(max(0.05, min(0.10, (1 - soc_usage) * 0.12)), 3)

    return {
        "std_dev_plugin_hrs": assumptions["plugin_hrs"],
        "std_dev_plugout_hrs": assumptions["plugout_hrs"],
        "std_dev_soc": soc_std,
    }


def load_archetypes() -> list[dict]:
    """
    Load and parse driver_types.csv into a list of archetype parameter dicts.
    Called once at startup by simulator.py and app.py.
    """
    df = pd.read_csv(CSV_PATH)

    # Normalise column names to snake_case
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"[^\w]+", "_", regex=True)
        .str.strip("_")
    )

    archetypes = []

    for _, row in df.iterrows():
        parsed = {
            "id": int(row[""]),                          # first column is archetype number
            "name": row["name"].strip(),
            "population_pct": _parse_pct(row["of_population"]),
            "miles_per_year": float(row["miles_yr"]),
            "battery_kwh": float(row["battery_kwh"]),
            "efficiency_mi_per_kwh": float(row["efficiency_mi_kwh"]),
            "plug_frequency": float(row["plug_in_frequency_per_day"]),
            "charger_kw": float(row["charger_kw"]),
            "plugin_time_hr": _parse_time_to_decimal(row["plug_in_time"]),
            "plugout_time_hr": _parse_time_to_decimal(row["plug_out_time"]),
            "target_soc": _parse_pct(row["target_soc"]),
            "kwh_per_year": float(row["kwh_year"]),
            "kwh_per_plugin": float(row["kwh_plug_in"]),
            "plugin_soc_mean": _parse_pct(row["plug_in_soc"]),
            "soc_requirement": _parse_pct(row["soc_requirement"]),
            "charging_duration_hrs": float(row["charging_duration_hrs"]),
        }

        # Append derived noise parameters
        parsed.update(_derive_std_devs(parsed))

        archetypes.append(parsed)

    return archetypes


# Module-level constants — import these everywhere else
ARCHETYPES = load_archetypes()
ARCHETYPE_NAMES = [a["name"] for a in ARCHETYPES]
ARCHETYPE_BY_ID = {a["id"]: a for a in ARCHETYPES}