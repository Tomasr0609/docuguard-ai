"""Streamlit page: Run evaluation harness and view results."""
import os
import subprocess
import json
from pathlib import Path

import streamlit as st
import pandas as pd

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
RESULTS_DIR = EVAL_DIR / "results"


st.set_page_config(page_title="Evaluación — DocuGuard AI Lite", page_icon="", layout="wide")
st.title("Evaluación del pipeline")

st.markdown(
    "Corré el harness de evaluación contra el dataset sintético etiquetado "
    "y obtené métricas de precisión de extracción, recall de hallazgos, y más."
)

col1, col2 = st.columns(2)
with col1:
    subset = st.number_input("Documentos a evaluar (0 = todos)", min_value=0, max_value=40, value=0)
with col2:
    use_full = st.checkbox("Pipeline completo (requiere API key)", value=False)

if st.button("Ejecutar evaluación", type="primary"):
    cmd = ["python", str(EVAL_DIR / "run_eval.py")]
    if use_full:
        cmd.append("--full")
    if subset > 0:
        cmd.extend(["--subset", str(subset)])

    with st.spinner("Ejecutando evaluación..."):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        st.error(f"Error en evaluación:\n{result.stderr}")
        st.code(result.stdout)
    else:
        st.success("Evaluación completada")
        st.code(result.stdout)

        # Show latest report
        reports = sorted(RESULTS_DIR.glob("*.md"), reverse=True)
        if reports:
            latest = reports[0]
            with open(latest, "r", encoding="utf-8") as f:
                content = f.read()
            st.markdown(content)

# Show historical reports
st.subheader("Reportes históricos")
reports = sorted(RESULTS_DIR.glob("*.md"), reverse=True)
if reports:
    selected_report = st.selectbox(
        "Seleccionar reporte",
        [r.name for r in reports],
    )
    if selected_report:
        report_path = RESULTS_DIR / selected_report
        with open(report_path, "r", encoding="utf-8") as f:
            st.markdown(f.read())
else:
    st.info("No hay reportes aún. Ejecutá una evaluación primero.")
