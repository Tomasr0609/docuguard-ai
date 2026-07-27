"""Streamlit page: Observability charts from traces.jsonl."""
import os
import json
from pathlib import Path

import streamlit as st
import pandas as pd

TRACES_PATH = Path(__file__).resolve().parent.parent / "logs" / "traces.jsonl"


st.set_page_config(page_title="Observabilidad — DocuGuard AI Lite", page_icon="", layout="wide")
st.title("Observabilidad")

st.markdown(
    "Métricas de costo, latencia y uso por agente. "
    "Los datos provienen de `logs/traces.jsonl`."
)

# Load traces
if not TRACES_PATH.exists():
    st.warning("No hay datos de trazabilidad. Procesá algunos documentos primero.")
    st.stop()

records = []
with open(TRACES_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

if not records:
    st.info("No hay registros de trazabilidad.")
    st.stop()

df = pd.DataFrame(records)

st.subheader(f"{len(records)} llamadas a LLM registradas")

# Cost over time
if "timestamp" in df.columns and "estimated_cost_usd" in df.columns:
    st.subheader("Costo acumulado")
    df_time = df.copy()
    df_time["ts"] = pd.to_datetime(df_time["timestamp"])
    df_time = df_time.sort_values("ts")
    df_time["cost_cumsum"] = df_time["estimated_cost_usd"].cumsum()
    st.line_chart(df_time.set_index("ts")["cost_cumsum"])

st.subheader("Métricas por agente")
if "agent_name" in df.columns:
    agent_stats = df.groupby("agent_name").agg(
        calls=("agent_name", "count"),
        total_cost=("estimated_cost_usd", "sum"),
        avg_latency_ms=("latency_ms", "mean"),
        max_latency_ms=("latency_ms", "max"),
        total_input_tokens=("input_tokens", "sum"),
        total_output_tokens=("output_tokens", "sum"),
    ).round(2)
    st.dataframe(agent_stats)

st.subheader("Latencia por agente")
if "agent_name" in df.columns and "latency_ms" in df.columns:
    lat_df = df.groupby("agent_name")["latency_ms"].mean().reset_index()
    st.bar_chart(lat_df.set_index("agent_name"))

st.subheader("Costo por agente")
if "agent_name" in df.columns and "estimated_cost_usd" in df.columns:
    cost_df = df.groupby("agent_name")["estimated_cost_usd"].sum().reset_index()
    st.bar_chart(cost_df.set_index("agent_name"))

st.subheader("Tasa de éxito")
if "agent_name" in df.columns and "success" in df.columns:
    success_df = df.groupby("agent_name")["success"].mean().reset_index()
    success_df["success"] = success_df["success"] * 100
    st.dataframe(success_df.rename(columns={"success": "tasa_exito_%"}))

st.subheader("Datos crudos")
if st.checkbox("Mostrar datos crudos"):
    st.dataframe(df)
