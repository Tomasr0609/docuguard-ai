"""DocuGuard AI Lite — Streamlit frontend (upload page)."""
import os
import time
from pathlib import Path

import streamlit as st
import httpx

API_BASE = os.environ.get("DOCUGUARD_API_URL", "http://127.0.0.1:8000")


def _api_url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"


st.set_page_config(
    page_title="DocuGuard AI Lite",
    page_icon="",
    layout="wide",
)

st.title("DocuGuard AI Lite")
st.markdown("Verificación de cumplimiento documental con IA multi-agente")

# Check API health
try:
    r = httpx.get(_api_url("health"), timeout=5)
    api_ok = r.status_code == 200
except Exception:
    api_ok = False

if not api_ok:
    st.warning(
        f"No se pudo conectar al backend en {API_BASE}. "
        "Asegurate de que el servidor FastAPI esté corriendo: "
        "`uvicorn backend.api.main:app --reload`"
    )

st.sidebar.header("DocuGuard AI Lite")
st.sidebar.markdown(
    """
- **Subir documento** ← estás acá
- Reportes
- Evaluación
- Observabilidad
"""
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**API:** " + ("Conectado" if api_ok else "Desconectado"),
    unsafe_allow_html=True,
)

# Upload section
st.header("Subir documento")
st.markdown("Subí un contrato, NDA o factura en formato PDF, PNG, JPG o TXT.")

col1, col2 = st.columns([3, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Seleccionar archivo",
        type=["pdf", "png", "jpg", "jpeg", "txt"],
        label_visibility="collapsed",
    )

with col2:
    st.markdown("### ")
    process_btn = st.button("Procesar", type="primary", disabled=not (uploaded_file and api_ok))

if process_btn and uploaded_file and api_ok:
    with st.spinner("Subiendo documento..."):
        files = {"file": (uploaded_file.name, uploaded_file.read(), uploaded_file.type)}
        r = httpx.post(_api_url("documents/upload"), files=files, timeout=30)

        if r.status_code == 200:
            data = r.json()
            doc_id = data["doc_id"]
            st.success(f"Documento subido exitosamente. ID: {doc_id}")
            st.info("El procesamiento está corriendo en segundo plano. "
                    "Andá a la página Reportes para ver el resultado.")
            if st.button("Ver reporte"):
                st.switch_page("pages/1_Reportes.py")
        else:
            st.error(f"Error al subir: {r.text}")

# Show recent documents
st.header("Documentos recientes")
if api_ok:
    r = httpx.get(_api_url("documents"), timeout=10)
    if r.status_code == 200:
        docs = r.json()
        if docs:
            for d in docs[:5]:
                risk = d.get("risk_level") or "pendiente"
                status = d.get("status", "?")
                st.markdown(
                    f"- **{d['doc_id']}** — {d.get('filename', '?')} "
                    f"| Estado: `{status}` | Riesgo: `{risk}`"
                )
            if len(docs) > 5:
                st.markdown(f"... y {len(docs) - 5} más. Ver todos en Reportes.")
        else:
            st.markdown("*No hay documentos aún. Subí uno arriba.*")
    else:
        st.error(f"Error al listar documentos: {r.status_code}")
else:
    st.markdown("*Esperando conexión al backend...*")
