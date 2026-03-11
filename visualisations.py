"""
visualisations.py
-----------------
All Plotly figure builders for the EV simulator dashboard.

Each function takes a DataFrame and returns a plotly Figure.
No Streamlit imports here — figures are passed to st.plotly_chart() in app.py.

Two sections:
1. Individual agent view  — Gantt timeline (the core brief deliverable)
2. Population view        — time-of-day charts, SoC distributions, demand ribbon
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ---------------------------------------------------------------------------
# Colour palette — consistent archetype colours across all charts
# ---------------------------------------------------------------------------

ARCHETYPE_COLOURS = {
    "Average (UK)":                "#4C72B0",
    "Intelligent Octopus average": "#DD8452",
    "Infrequent charging":         "#55A868",
    "Infrequent driving":          "#C44E52",
    "Scheduled charging":          "#8172B2",
    "Always plugged-in":           "#937860",
}


# ---------------------------------------------------------------------------
# Section 1: Individual agent view
# ---------------------------------------------------------------------------

def plot_agent_gantt(
    plug_events_df: pd.DataFrame,
    n_agents: int = 10,
    n_days: int = 7,
    start_date=None,
) -> go.Figure:
    """
    Gantt-style chart showing plug events for each agent.
    Each bar spans plugin_dt to plugout_dt, coloured by archetype.
    Bar opacity reflects plug-in SoC — darker = lower SoC = more charge needed.

    Uses px.timeline which handles datetime ranges natively.
    """
    if plug_events_df.empty:
        return go.Figure()

    # Filter to date range
    if start_date is None:
        start_date = plug_events_df["plugin_dt"].min().normalize()
    end_date = start_date + pd.Timedelta(days=n_days)
    df = plug_events_df[plug_events_df["plugin_dt"] < end_date].copy()

    # Sample agents — take first N by agent_id for consistency
    all_agents = sorted(df["agent_id"].unique())
    selected_agents = all_agents[:n_agents]
    df = df[df["agent_id"].isin(selected_agents)].copy()

    if df.empty:
        return go.Figure()

    # Add readable hover columns
    df["plugin_soc_pct"] = (df["plugin_soc"] * 100).round(1).astype(str) + "%"
    df["plugout_soc_pct"] = (df["plugout_soc"] * 100).round(1).astype(str) + "%"

    fig = px.timeline(
        df,
        x_start="plugin_dt",
        x_end="plugout_dt",
        y="agent_id",
        color="archetype",
        color_discrete_map=ARCHETYPE_COLOURS,
        hover_data={
            "agent_id": True,
            "archetype": True,
            "plugin_soc_pct": True,
            "plugout_soc_pct": True,
            "kwh_delivered": ":.1f",
            "plug_duration_hrs": ":.1f",
            "plugin_dt": False,
            "plugout_dt": False,
        },
        labels={
            "agent_id": "Agent",
            "plugin_soc_pct": "Plug-in SoC",
            "plugout_soc_pct": "Plug-out SoC",
            "kwh_delivered": "kWh delivered",
            "plug_duration_hrs": "Duration (hrs)",
        },
        title="Agent Plug Event Timeline",
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        height=max(400, n_agents * 32),
        plot_bgcolor="white",
        legend=dict(title="Archetype", orientation="v"),
        xaxis=dict(title="Date"),
        yaxis=dict(title="Agent", tickfont=dict(size=9)),
    )

    # Add plug-in/out time annotations when few days shown — avoids overlap
    if n_days <= 3:
        agent_order = sorted(df["agent_id"].unique())  # compute once outside loop
        for _, row in df.iterrows():
            plugin_label = row["plugin_dt"].strftime("%H:%M")
            plugout_label = row["plugout_dt"].strftime("%H:%M")
            mid_dt = row["plugin_dt"] + (row["plugout_dt"] - row["plugin_dt"]) / 2

            fig.add_annotation(
                x=mid_dt,
                y=row["agent_id"],
                text=f"{plugin_label}→{plugout_label}",
                showarrow=False,
                font=dict(size=8, color="white"),
                xanchor="center",
                yanchor="middle",
            )

    return fig


# ---------------------------------------------------------------------------
# Section 2: Population view
# ---------------------------------------------------------------------------

def plot_plugged_in_by_hour(
    halfhourly_df: pd.DataFrame,
    plug_events_df: pd.DataFrame,
) -> go.Figure:
    """
    Bar chart of % agents plugged in by hour of day, stacked by archetype.
    Averaged across all days in the simulation.

    Note: re-filters plug_events_df per slot to get archetype breakdown.
    For large simulations (1000+ agents, 90 days) this is the main performance
    bottleneck — a natural optimisation would be to pre-compute archetype
    breakdowns in _build_halfhourly_grid.
    """
    if halfhourly_df.empty or plug_events_df.empty:
        return go.Figure()

    records = []
    for _, slot_row in halfhourly_df.iterrows():
        slot_ts = pd.Timestamp(slot_row["slot"])
        mask = (
            (plug_events_df["plugin_dt"] <= slot_ts) &
            (plug_events_df["plugout_dt"] > slot_ts)
        )
        plugged = plug_events_df[mask]
        for archetype in ARCHETYPE_COLOURS:
            n = (plugged["archetype"] == archetype).sum()
            records.append({
                "hour_of_day": slot_row["hour_of_day"],
                "archetype": archetype,
                "n_plugged": n,
            })

    df = pd.DataFrame(records)
    df = df.groupby(["hour_of_day", "archetype"])["n_plugged"].mean().reset_index()
    total_per_slot = df.groupby("hour_of_day")["n_plugged"].transform("sum")
    df["pct_plugged"] = df["n_plugged"] / total_per_slot.replace(0, 1)

    fig = px.bar(
        df,
        x="hour_of_day",
        y="pct_plugged",
        color="archetype",
        color_discrete_map=ARCHETYPE_COLOURS,
        labels={
            "hour_of_day": "Hour of Day",
            "pct_plugged": "% of Plugged-in Agents",
        },
        title="% Plugged In by Hour of Day (by Archetype)",
    )
    fig.update_layout(
        xaxis=dict(tickmode="linear", tick0=0, dtick=2),
        yaxis=dict(tickformat=".0%"),
        plot_bgcolor="white",
        legend=dict(title="Archetype"),
    )
    return fig


def plot_soc_distribution(plug_events_df: pd.DataFrame) -> go.Figure:
    """
    Box plot of plug-in SoC by archetype.
    Shows variation in battery state when drivers connect — key for
    understanding demand flexibility.
    """
    if plug_events_df.empty:
        return go.Figure()

    fig = go.Figure()

    for archetype, colour in ARCHETYPE_COLOURS.items():
        data = plug_events_df[plug_events_df["archetype"] == archetype]["plugin_soc"] * 100
        if data.empty:
            continue
        fig.add_trace(go.Box(
            y=data,
            name=archetype,
            marker_color=colour,
            boxmean=True,
            hovertemplate=(
                f"<b>{archetype}</b><br>"
                "Plug-in SoC: %{y:.1f}%<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Plug-in State of Charge by Archetype",
        yaxis=dict(title="Plug-in SoC (%)", range=[0, 100]),
        xaxis=dict(title="Archetype"),
        plot_bgcolor="white",
        showlegend=False,
        height=450,
    )
    return fig


def plot_kwh_demand_by_hour(halfhourly_df: pd.DataFrame) -> go.Figure:
    """
    Bar chart of total kWh demand by hour of day, averaged across simulation days.
    Shows when grid load from EV charging is highest.
    """
    if halfhourly_df.empty:
        return go.Figure()

    df = (
        halfhourly_df
        .groupby("hour_of_day")["total_kwh_demand"]
        .mean()
        .reset_index()
    )

    fig = px.bar(
        df,
        x="hour_of_day",
        y="total_kwh_demand",
        labels={
            "hour_of_day": "Hour of Day",
            "total_kwh_demand": "Avg kWh Demand",
        },
        title="Average kWh Demand by Hour of Day",
        color_discrete_sequence=["#4C72B0"],
    )

    # Highlight evening peak (5-8pm) — reference CNZ report
    fig.add_vrect(
        x0=17, x1=20,
        fillcolor="red", opacity=0.08,
        annotation_text="Evening peak",
        annotation_position="top left",
    )

    fig.update_layout(
        xaxis=dict(tickmode="linear", tick0=0, dtick=2),
        plot_bgcolor="white",
    )
    return fig


def plot_soc_ribbon(plug_events_df: pd.DataFrame) -> go.Figure:
    """
    Line chart of mean plug-in SoC over simulation period with
    5th-95th percentile shaded band. Shows population-level SoC
    stability over time.
    """
    if plug_events_df.empty:
        return go.Figure()

    df = plug_events_df.copy()
    df["date"] = df["plugin_dt"].dt.normalize()

    daily = (
        df.groupby("date")["plugin_soc"]
        .agg(
            mean="mean",
            p05=lambda x: x.quantile(0.05),
            p95=lambda x: x.quantile(0.95),
        )
        .reset_index()
    )
    daily[["mean", "p05", "p95"]] = daily[["mean", "p05", "p95"]] * 100

    fig = go.Figure()

    # Shaded band
    fig.add_trace(go.Scatter(
        x=pd.concat([daily["date"], daily["date"].iloc[::-1]]),
        y=pd.concat([daily["p95"], daily["p05"].iloc[::-1]]),
        fill="toself",
        fillcolor="rgba(76, 114, 176, 0.15)",
        line=dict(color="rgba(255,255,255,0)"),
        name="5th–95th percentile",
        hoverinfo="skip",
    ))

    # Mean line
    fig.add_trace(go.Scatter(
        x=daily["date"],
        y=daily["mean"],
        mode="lines",
        line=dict(color="#4C72B0", width=2),
        name="Mean plug-in SoC",
    ))

    fig.update_layout(
        title="Population Plug-in SoC Over Time",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Plug-in SoC (%)", range=[0, 100]),
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig