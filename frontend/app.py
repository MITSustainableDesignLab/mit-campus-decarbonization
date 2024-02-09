import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend import frontend_settings as settings
from lib.client import client
from lib.supa import Building

st.set_page_config(layout="wide", page_title="MIT Decarbonization")


@st.cache_data
def get_all_buildings():
    df = pd.DataFrame(client.table("Building").select("*").execute().data).set_index(
        "id"
    )
    # create csv bytes
    csv = df.to_csv().encode()
    return df, csv


@st.cache_data
def get_building_scenarios(building_id: int):
    ids = (
        client.table("DemandScenarioBuilding")
        .select("id, demand_scenario_id")
        .eq("building_id", building_id)
        .execute()
        .data
    )
    scenario_ids = [d["demand_scenario_id"] for d in ids]
    results_ids = [d["id"] for d in ids]
    return scenario_ids, results_ids


@st.cache_data
def get_scenarios():
    return client.table("DemandScenario").select("*").execute().data


@st.cache_data
def get_scenario_results(scenario_id: int):
    ids = (
        client.table("DemandScenarioBuilding")
        .select("id")
        .eq("demand_scenario_id", scenario_id)
        .execute()
        .data
    )
    results_ids = [d["id"] for d in ids]
    results = (
        client.table("BuildingSimulationResult")
        .select("*")
        .in_("id", results_ids)
        .execute()
        .data
    )
    dfs = []
    for result in results:
        result["heating"] = json.loads(result["heating"])
        result["cooling"] = json.loads(result["cooling"])
        result["lighting"] = json.loads(result["lighting"])
        result["equipment"] = json.loads(result["equipment"])
        df = pd.DataFrame(
            {
                "heating": result["heating"],
                "cooling": result["cooling"],
                "lighting": result["lighting"],
                "equipment": result["equipment"],
            }
        )
        df["Timestamp"] = pd.date_range(start="2024-01-01", periods=len(df), freq="h")
        df = df.set_index("Timestamp")
        df["result_id"] = result["id"]
        df = df.set_index("result_id", append=True)
        dfs.append(df)
    df_buildings = pd.concat(dfs)
    df = df_buildings.groupby("Timestamp").sum()
    df.columns = [x.capitalize() for x in df.columns]
    df = df.reset_index("Timestamp")
    df_melted = df.melt(
        id_vars=["Timestamp"], var_name="End Use", value_name="Energy [J]"
    )
    return df, df_melted, df_buildings


@st.cache_data
def get_scenario_building_result(scenario_id: int, building_id: int):
    ids = (
        client.table("DemandScenarioBuilding")
        .select("id")
        .eq("demand_scenario_id", scenario_id)
        .eq("building_id", building_id)
        .execute()
        .data
    )
    results_ids = [d["id"] for d in ids]
    results = (
        client.table("BuildingSimulationResult")
        .select("*")
        .in_("id", results_ids)
        .execute()
        .data
    )
    df = pd.DataFrame(
        {
            "heating": json.loads(results[0]["heating"]),
            "cooling": json.loads(results[0]["cooling"]),
            "lighting": json.loads(results[0]["lighting"]),
            "equipment": json.loads(results[0]["equipment"]),
        }
    )
    df["Timestamp"] = pd.date_range(start="2024-01-01", periods=len(df), freq="h")
    df.columns = [x.capitalize() for x in df.columns]
    df_melted = df.melt(
        id_vars=["Timestamp"], var_name="End Use", value_name="Energy [J]"
    )

    return df, df_melted


ENDUSE_PASTEL_COLORS = {
    "Heating": "#FF7671",
    "Cooling": "#6D68E6",
    "Lighting": "#FFD700",
    "Equipment": "#90EE90",
}


def render_title():
    st.title("MIT Decarbonization")


def render_buildings():
    all_buildings, all_buildings_csv = get_all_buildings()
    st.download_button(
        "Download all building metadata",
        all_buildings_csv,
        "buildings_metadata.csv",
        "Download all buildings",
        use_container_width=True,
        type="primary",
    )
    building_id = st.selectbox(
        "Building",
        all_buildings.index,
        format_func=lambda x: all_buildings.loc[x, "name"],
        help="Select a building to view its data",
    )
    building = all_buildings.loc[building_id]
    scenario_ids, results_ids = get_building_scenarios(building_id)
    all_scenarios = get_scenarios()
    filtered_scenarios = [s for s in all_scenarios if s["id"] in scenario_ids]
    l, r = st.columns(2)
    with l:
        scenario_id = st.selectbox(
            "Building Demand Scenario",
            scenario_ids,
            format_func=lambda x: [
                s["name"] for s in filtered_scenarios if s["id"] == x
            ][0],
            help="Select a demand scenario to view its data",
        )
        result, result_melted = get_scenario_building_result(scenario_id, building_id)
        fig = px.line(
            result_melted,
            x="Timestamp",
            y="Energy [J]",
            color="End Use",
            title=f"Building {building['name']} Energy Use",
            color_discrete_map=ENDUSE_PASTEL_COLORS,
        )
        st.plotly_chart(fig, use_container_width=True)

    with r:
        st.dataframe(building)


def render_building_scenarios():
    all_scenarios = get_scenarios()
    scenario = st.selectbox(
        "Demand Scenario",
        all_scenarios,
        format_func=lambda x: x["name"],
        help="Select a demand scenario to view its data",
    )
    df, df_melted, df_buildings = get_scenario_results(scenario["id"])
    l, r = st.columns(2)
    with l:
        st.download_button(
            "Download scenario results",
            df.to_csv().encode(),
            f"{scenario['name']}_results.csv",
            "Download scenario results",
            use_container_width=True,
            type="primary",
        )
    with r:
        st.download_button(
            "Download scenario buildings results",
            df_buildings.to_csv().encode(),
            f"{scenario['name']}_buildings_results.csv",
            "Download scenario buildings results",
            use_container_width=True,
            type="primary",
        )
    fig = px.line(
        df_melted,
        x="Timestamp",
        y="Energy [J]",
        color="End Use",
        title=f"{scenario['name']} Demand Scenario",
        color_discrete_map=ENDUSE_PASTEL_COLORS,
    )
    st.plotly_chart(fig, use_container_width=True)


def password_protect():
    if "password" not in st.session_state:
        st.session_state.password = None
    if st.session_state.password == settings.password:
        return True
    else:
        password = st.text_input("Password", type="password")
        st.session_state.password = password
        return st.session_state.password == settings.password


render_title()
logged_in = password_protect()
if logged_in:
    buildings_tab, scenarios_tab = st.tabs(["Buildings", "Scenarios"])
    with buildings_tab:
        render_buildings()
    with scenarios_tab:
        render_building_scenarios()