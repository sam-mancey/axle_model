"""
app.py
------
Streamlit dashboard for the EV driver behaviour simulator.

Structure:
- Sidebar: simulation controls and per-archetype overrides
- Section 1: Individual agent view (core brief deliverable)
- Section 2: Population-level charts

Run with: streamlit run app.py
"""

import streamlit as st
from archetypes import ARCHETYPES
from simulator import build_agents, run_simulation
from visualisations import (
    plot_agent_gantt,
    plot_plugged_in_by_hour,
    plot_soc_distribution,
    plot_kwh_demand_by_hour,
    plot_soc_ribbon,
)
from config import (
    SIMULATION_DEFAULTS,
    PLUGIN_TIME_OFFSETS,
    POPULATION_WEIGHT_OVERRIDES,
)

st.set_page_config(
    page_title="EV Driver Simulator",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ EV Driver Behaviour Simulator")
st.caption("Agent-based simulation calibrated against Octopus Centre for Net Zero (May 2022)")

# ---------------------------------------------------------------------------
# Sidebar — simulation controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Simulation Settings")

    n_agents = st.slider(
        "Number of agents",
        min_value=50,
        max_value=1000,
        value=SIMULATION_DEFAULTS["n_agents"],
        step=50,
    )
    n_days = st.slider(
        "Days to simulate",
        min_value=7,
        max_value=90,
        value=SIMULATION_DEFAULTS["n_days"],
        step=7,
    )
    seed = st.number_input(
        "Random seed (for reproducibility)",
        min_value=0,
        max_value=9999,
        value=SIMULATION_DEFAULTS["random_seed"],
        step=1,
    )

    st.divider()
    st.subheader("Population Mix")
    st.caption("Adjust relative weight of each archetype. Values are normalised automatically.")

    pop_weights = {}
    for a in ARCHETYPES:
        name = a["name"]
        pop_weights[name] = st.slider(
            name,
            min_value=0.0,
            max_value=1.0,
            value=POPULATION_WEIGHT_OVERRIDES[name],
            step=0.01,
            key=f"pop_{name}",
        )

    st.divider()
    st.subheader("Plug-in Time Offsets (hrs)")
    st.caption("Shift each archetype's mean plug-in time earlier (−) or later (+).")

    time_offsets = {}
    for a in ARCHETYPES:
        name = a["name"]
        time_offsets[name] = st.slider(
            name,
            min_value=-3.0,
            max_value=3.0,
            value=PLUGIN_TIME_OFFSETS[name],
            step=0.25,
            key=f"offset_{name}",
        )

    st.divider()
    run_button = st.button("▶ Run Simulation", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Run simulation
# ---------------------------------------------------------------------------

# Auto-run on first load; re-run only when button is pressed
if "plug_events" not in st.session_state or run_button:
    with st.spinner("Running simulation..."):
        agents = build_agents(
            n_agents=n_agents,
            weights=pop_weights,
            seed=seed,
        )
        plug_events, halfhourly = run_simulation(
            agents=agents,
            n_days=n_days,
            seed=seed,
            plugin_time_offsets=time_offsets,
        )
        st.session_state["plug_events"] = plug_events
        st.session_state["halfhourly"] = halfhourly

plug_events = st.session_state["plug_events"]
halfhourly = st.session_state["halfhourly"]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total plug events", f"{len(plug_events):,}")
col2.metric("Avg plug-in SoC", f"{plug_events['plugin_soc'].mean()*100:.1f}%")
col3.metric("Avg kWh per session", f"{plug_events['kwh_delivered'].mean():.1f} kWh")
col4.metric("Avg plug duration", f"{plug_events['plug_duration_hrs'].mean():.1f} hrs")

st.divider()

# ---------------------------------------------------------------------------
# Section 1: Individual agent view
# ---------------------------------------------------------------------------

st.header("Individual Agent View")
st.caption("When is each agent plugged in, and what is their state of charge at plug-in? Bar opacity reflects plug-in SoC — darker = lower SoC = more charge needed.")

gantt_col1, gantt_col2 = st.columns([1, 4])
with gantt_col1:
    gantt_n_agents = st.slider(
        "Agents to display",
        min_value=5,
        max_value=min(n_agents, 200),
        value=min(10, n_agents),
        step=5,
    )
    gantt_n_days = st.slider(
        "Days to display",
        min_value=1,
        max_value=n_days,
        value=min(7, n_days),
        step=1,
    )

with gantt_col2:
    st.plotly_chart(
        plot_agent_gantt(
            plug_events,
            n_agents=gantt_n_agents,
            n_days=gantt_n_days,
        ),
        use_container_width=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Population view
# ---------------------------------------------------------------------------

st.header("Population View")

row1_col1, row1_col2 = st.columns(2)

with row1_col1:
    st.plotly_chart(
        plot_plugged_in_by_hour(halfhourly, plug_events),
        use_container_width=True,
    )

with row1_col2:
    st.plotly_chart(
        plot_kwh_demand_by_hour(halfhourly),
        use_container_width=True,
    )

row2_col1, row2_col2 = st.columns(2)

with row2_col1:
    st.plotly_chart(
        plot_soc_distribution(plug_events),
        use_container_width=True,
    )

with row2_col2:
    st.plotly_chart(
        plot_soc_ribbon(plug_events),
        use_container_width=True,
    )