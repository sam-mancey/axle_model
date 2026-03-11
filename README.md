EV Driver Behaviour Simulator
An agent-based simulator of EV driver charging behaviour, built as a take-home exercise for Axle Energy. The simulator models individual EV drivers, captures population-level charging patterns, and visualises both through an interactive Streamlit dashboard.
Calibrated against the Octopus Centre for Net Zero report (May 2022).

Quickstart
bashpip install -r requirements.txt
streamlit run app.py

Project Structure
├── app.py              # Streamlit dashboard — UI and layout only
├── simulator.py        # Core simulation engine — EVDriver class and run logic
├── archetypes.py       # Loads and parses driver_types.csv into archetype dicts
├── visualisations.py   # Plotly figure builders — no Streamlit imports
├── config.py           # Central assumptions file — edit here to change behaviour
├── driver_types.csv    # Archetype definitions (source of truth)
└── requirements.txt

How It Works
Archetypes
Six EV driver archetypes are loaded from driver_types.csv, derived from Axle's population segmentation and calibrated against the CNZ report. Each archetype defines plug-in time, plug-out time, battery size, charger power, plug-in frequency, and state of charge (SoC) at plug-in.
Gaussian noise parameters controlling within-archetype variation are not in the CSV — they are defined in config.py and applied at load time by archetypes.py. This separates assumptions from data.
Simulation
build_agents() creates a population of EVDriver agents by weighted random sampling from the archetypes. Weights default to the population percentages in the CSV but can be overridden via the dashboard sidebar.
run_simulation() runs a daily loop over all agents. Each day, each agent:

Makes a Bernoulli draw against plug_frequency to decide whether to plug in
Samples a plug-in time with Gaussian noise around the archetype mean
Samples a plug-out time — overnight events correctly span the midnight boundary as single continuous events
Samples a plug-in SoC with Gaussian noise
Derives plug-out SoC and kWh delivered from a constant charge rate model (charger_kw × charging_hrs / battery_kwh), capped at target_soc

If an agent plugs in above their target SoC, the plug event is still recorded but zero charge is delivered — reflecting the habitual plug-in behaviour observed in the CNZ data.
Noise is re-sampled every day per agent for realistic variation. A fixed random seed ensures results are fully reproducible.
Outputs
The simulation returns two DataFrames:
plug_events_df — one row per plug event:
Column              
Description
agent_id            Unique agent identifier
archetype           Archetype name
plugin_dt           Plug-in datetime
plugout_dt          Plug-out datetime
plugin_soc          State of charge at plug-in (0–1)
plugout_soc         State of charge at plug-out (0–1)
kwh_delivered       Energy delivered during session
charging_hrs        Time actively charging (< plug duration)
plug_duration_hrs   Total time connectedcharger_kwCharger power rating
halfhourly_df — half-hourly time series:
Column              Description
slot                Half-hour slot 
datetimehour_of_day Decimal hour (e.g. 18.5 = 6:30pm)
pct_plugged_in      Fraction of agents connected
mean_plugin_soc     Mean SoC of connected 
agentstotal_kwh_demand  Total kWh actively drawn this slot

Dashboard
The dashboard has two sections:
Individual Agent View — a Gantt timeline showing every plug event per agent. Directly answers the brief: when is each agent plugged in and at what SoC? Configurable number of agents and days. Timestamps shown on bars when ≤ 3 days displayed.
Population View — four charts showing population-level patterns:

% plugged in by hour of day, broken down by archetype
Average kWh demand by hour of day (with evening peak highlighted)
Plug-in SoC distribution by archetype (box plot)
Population SoC over time with 5th–95th percentile ribbon


Configuration
All modifiable assumptions live in config.py:
SIMULATION_DEFAULTS — default number of agents, days, and random seed.
POPULATION_WEIGHT_OVERRIDES — default archetype population weights for the sidebar sliders. These are relative weights, normalised to sum to 1 at runtime.
PLUGIN_TIME_OFFSETS — default plug-in time offsets (hours) per archetype. Used as starting values for the sidebar sliders.
STD_DEV_ASSUMPTIONS — Gaussian noise parameters per archetype. Controls how much within-archetype variation is applied to plug-in times and SoC. Edit these to explore sensitivity to behavioural assumptions without touching simulation logic.
The sidebar exposes live controls for agents, days, seed, population weights, and plug-in time offsets. Changes take effect when "▶ Run Simulation" is pressed.

Key Design Decisions
Agent-based, not population-based — each agent is an individual with its own archetype and daily noise draws. This allows individual behaviour to be inspected directly (Gantt view) while still producing population-level statistics.
Plug events span midnight — a plug-in at 6pm with plug-out at 7am the next day is stored as a single event with full datetimes, not split at midnight. This keeps duration and SoC calculations correct.
Charging ends before plug-out — charging_end_dt = plugin_dt + charging_hrs is tracked separately from plugout_dt. A car that finishes charging at 8:30pm but isn't unplugged until 7am contributes to pct_plugged_in overnight but draws zero kWh after 8:30pm. This is the key distinction that produces a physically correct kWh demand profile.
Zero charge events are preserved — agents who plug in above their target SoC still generate a plug event with kwh_delivered = 0. They appear in the Gantt and in pct_plugged_in but not in kWh demand. This reflects habitual plug-in behaviour observed in the CNZ data.
Assumptions separated from logic — config.py is the only file that needs to be edited to change behavioural assumptions. simulator.py and archetypes.py contain no hardcoded values.

Known Limitations and Natural Extensions
Constant charge rate — the model assumes charging at charger_kw throughout. In reality, EVs taper charge rate above ~80% SoC to protect battery health. This is a natural extension that would require a piecewise charge rate model.
No weekday/weekend split — the CNZ report shows different plug-in and plug-out patterns on weekends (later plug-out, more midday sessions). Adding a day_type flag per simulation day and separate archetype parameters for weekdays vs weekends would improve realism.
Performance at scale — the % plugged in by hour chart re-filters the plug events DataFrame for every half-hour slot (O(n_slots × n_events)). This is acceptable for up to ~500 agents but would benefit from pre-computing archetype breakdowns in _build_halfhourly_grid for larger populations.
No Vehicle-to-Grid (V2G) — the simulator models charging only. Modelling discharge back to the grid would require tracking SoC continuously throughout the plug event rather than just at plug-in and plug-out.
Flexibility quantification — the logical next step for Axle's use case would be to compute, for each plug event, how many kWh could be shifted outside the 5–8pm evening peak while still meeting target_soc by plugout_dt. This would directly quantify the grid flexibility available from the simulated population.

Data Sources

Octopus Centre for Net Zero — Learning from Intelligent Octopus (May 2022)
Axle Energy archetype definitions (driver_types.csv)