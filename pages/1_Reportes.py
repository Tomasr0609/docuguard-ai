"""Streamlit page: Document reports list and detail."""
import os
import time
from pathlib import Path

import streamlit as st
import httpx
import pandas as pd

API_BASE = os.environ.get("DOCUGUARD_API_URL", "http://127.0.0.1:8000")

# Cada cuántos segundos se re-consulta el backend mientras el documento
# sigue en pending/processing.
AUTO_REFRESH_SECONDS = 4


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

# Si venimos recién de subir un documento (app.py guardó el doc_id en
# session_state), preseleccionarlo automáticamente en el dropdown.
default_index = 0
last_uploaded = st.session_state.get("last_uploaded_doc_id")
if last_uploaded and last_uploaded in doc_ids:
    default_index = doc_ids.index(last_uploaded)

selected_label = st.selectbox("Seleccionar documento", doc_labels, index=default_index)
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

# --- Auto-refresh mientras el documento sigue procesándose -----------------
# Se ubica DESPUÉS de mostrar el estado actual, para que la persona vea
# el "pending"/"processing" en pantalla antes de que dispare el próximo
# refresh. Solo se activa cuando corresponde, así no recarga documentos
# ya terminados.
if status in ("pending", "processing"):
    with st.spinner(f"Actualizando estado automáticamente cada {AUTO_REFRESH_SECONDS}s..."):
        time.sleep(AUTO_REFRESH_SECONDS)
    st.rerun()
# -----------------------------------------------------------------------------

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

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    if st.button("Exportar como JSON"):
        import json
        st.download_button(
            label="Descargar JSON",
            data=json.dumps(detail, ensure_ascii=False, indent=2),
            file_name=f"{doc_id}_report.json",
            mime="application/json",
        )
with col_b:
    if st.button("Volver a procesar"):
        st.info("Funcionalidad no disponible desde la UI. Usá la API.")

with col_c:
    confirm_key = f"confirm_delete_{doc_id}"
    if st.button("Eliminar documento", type="secondary"):
        st.session_state[confirm_key] = True

    if st.session_state.get(confirm_key):
        st.warning("¿Estás seguro de eliminar este documento?")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Sí, eliminar", key=f"yes_{doc_id}"):
                r = httpx.delete(_api_url(f"documents/{doc_id}"), timeout=10)
                if r.status_code == 200:
                    st.success("Documento eliminado.")
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                else:
                    st.error(f"Error al eliminar: {r.text}")
        with col_no:
            if st.button("Cancelar", key=f"no_{doc_id}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()

with col_d:
    confirm_all_key = "confirm_delete_all"
    if st.button("Eliminar todos", type="secondary"):
        st.session_state[confirm_all_key] = True

    if st.session_state.get(confirm_all_key):
        st.error("¿Eliminar TODOS los documentos? Esta acción no se puede deshacer.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Sí, eliminar todos", key="yes_all"):
                r = httpx.delete(_api_url("documents/clear"), timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    st.success(f"{data['deleted_count']} documento(s) eliminado(s).")
                    st.session_state.pop(confirm_all_key, None)
                    st.rerun()
                else:
                    st.error(f"Error al eliminar: {r.text}")
        with col_no:
            if st.button("Cancelar", key="no_all"):
                st.session_state.pop(confirm_all_key, None)
                st.rerun()
