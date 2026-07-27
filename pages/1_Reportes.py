"""Streamlit page: Document reports list and detail."""
import os
from pathlib import Path

import streamlit as st
import httpx
import pandas as pd

API_BASE = os.environ.get("DOCUGUARD_API_URL", "http://127.0.0.1:8000")


def _api_url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"


st.set_page_config(page_title="Reportes — DocuGuard AI Lite", page_icon="", layout="wide")
st.title("Reportes de documentos")

# Fetch all documents
try:
    r = httpx.get(_api_url("documents"), timeout=10)
    if r.status_code != 200:
        st.error(f"Error al obtener documentos: {r.status_code}")
        st.stop()
    docs = r.json()
except Exception as e:
    st.error(f"No se pudo conectar al backend: {e}")
    st.info("Asegurate de que el servidor FastAPI esté corriendo en " + API_BASE)
    st.stop()

if not docs:
    st.info("No hay documentos procesados. Subí uno desde la página principal.")
    st.stop()

# Document selector
doc_ids = [d["doc_id"] for d in docs]
doc_labels = [
    f"{d['doc_id']} — {d.get('filename', '?')} ({d.get('status', '?')})"
    for d in docs
]

selected_label = st.selectbox("Seleccionar documento", doc_labels)
selected_idx = doc_labels.index(selected_label)
selected_doc = docs[selected_idx]
doc_id = selected_doc["doc_id"]

# Fetch detail
r = httpx.get(_api_url(f"documents/{doc_id}"), timeout=10)
if r.status_code != 200:
    st.error(f"Error al obtener detalle: {r.status_code}")
    st.stop()

detail = r.json()

# Display report
st.header(f"Reporte: {doc_id}")
st.markdown(f"**Archivo:** {detail.get('filename', '?')}")

col1, col2, col3 = st.columns(3)
with col1:
    status = detail.get("status", "?")
    st.metric("Estado", status)
with col2:
    risk = detail.get("risk_level") or "—"
    st.metric("Riesgo global", risk)
with col3:
    score = detail.get("risk_score")
    st.metric("Score de riesgo", f"{score:.2f}" if score else "—")

if status in ("pending", "processing"):
    st.info("El documento está siendo procesado. Los valores de costo, score y tiempo aparecerán al finalizar.")
else:
    tiempo = detail.get("processing_time_ms")
    st.markdown(f"**Tiempo de procesamiento:** {tiempo} ms" if tiempo is not None else "**Tiempo de procesamiento:** —")
    costo = detail.get("total_cost_usd")
    st.markdown(f"**Costo estimado:** ${costo:.4f} USD" if costo is not None else "**Costo estimado:** —")

# Findings
st.subheader("Hallazgos")
findings = detail.get("findings", [])
if not findings:
    st.success("No se detectaron hallazgos. Documento conforme.")
else:
    for f in findings:
        sev = f.get("severity", "medium")
        sev_color = {"high": "red", "medium": "orange", "low": "green"}.get(sev, "gray")
        st.markdown(
            f"<span style='background-color:{sev_color}; padding:2px 8px; "
            f"border-radius:4px; color:white; font-weight:bold;'>{sev.upper()}</span> "
            f"**{f.get('type', '?')}** — {f.get('description', '')}",
            unsafe_allow_html=True,
        )
        snippet = f.get("source_snippet")
        if snippet:
            st.markdown(f"> Cita: \"{snippet}\"")
        ref = f.get("reference_clause")
        if ref:
            with st.expander("Ver cláusula de referencia"):
                st.markdown(ref)
        st.markdown("---")

# Summary
exec_summary = detail.get("executive_summary")
if exec_summary:
    st.subheader("Resumen ejecutivo")
    st.markdown(exec_summary)

# Actions
st.subheader("Acciones")

col1, col2 = st.columns(2)
with col1:
    if st.button("Exportar como JSON"):
        import json
        st.download_button(
            label="Descargar JSON",
            data=json.dumps(detail, ensure_ascii=False, indent=2),
            file_name=f"{doc_id}_report.json",
            mime="application/json",
        )
with col2:
    if st.button("Volver a procesar"):
        # Re-upload the file
        st.info("Funcionalidad no disponible desde la UI. Usá la API.")
