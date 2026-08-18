import logging
import os
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import httpx
import uvicorn

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("DOCUGUARD_API_URL", "http://127.0.0.1:8000")
UPLOAD_COOLDOWN_SECONDS = 60
AUTO_REDIRECT_SECONDS = 2


def _api_url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"


def _cooldown_remaining() -> float:
    """Segundos que faltan para poder subir otro documento.

    El backend es la fuente de verdad primaria: consultamos GET /documents/cooldown,
    que sobrevive a F5 y a navegación entre páginas porque el estado vive del
    lado del servidor (data/cooldown.json), no en el navegador.

    Solo si el request al backend falla (timeout, backend caído), caemos a un
    fallback LOCAL con session_state['last_upload_time'] para no romper la UX
    en ese edge case. Ese fallback NO sobrevive a un F5, pero es mejor que nada.
    """
    try:
        r = httpx.get(_api_url("documents/cooldown"), timeout=5)
        if r.status_code == 200:
            return float(r.json().get("cooldown_remaining", 0.0))
    except Exception:
        pass

    last_upload_time = st.session_state.get("last_upload_time")
    if last_upload_time is not None:
        return max(0.0, UPLOAD_COOLDOWN_SECONDS - (time.time() - last_upload_time))
    return 0.0


def _goto_reportes() -> None:
    st.session_state.pop("auto_redirect_until", None)
    st.session_state.pop("upload_success_msg", None)
    st.session_state.pop("upload_info_msg", None)
    st.switch_page("pages/1_Reportes.py")


# ---------------------------------------------------------------------------
# Backend auto-start
#
# Streamlit Community Cloud solo ejecuta `streamlit run app.py` (no permite
# levantar uvicorn en una terminal aparte), así que arrancamos el backend de
# FastAPI en un hilo en segundo plano la primera vez que se carga la app.
#
# Singleton: la variable a nivel de módulo persiste entre reruns porque
# Streamlit re-ejecuta app.py dentro del MISMO proceso Python. Una vez
# arrancado (o detectado como ya corriendo), nunca se vuelve a intentar.
#
# Compatibilidad local: si el puerto ya está ocupado (uvicorn manual en la
# segunda terminal), lo detectamos y no duplicamos el backend.
# ---------------------------------------------------------------------------
_backend_started = False
_backend_lock = threading.Lock()


def _backend_port() -> int:
    try:
        return urlparse(API_BASE).port or 8000
    except ValueError:
        return 8000


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """True si ya hay algo escuchando en host:port (bind falla).

    NO usamos SO_REUSEADDR: en Windows ese flag permite que dos sockets se
    bindeen al mismo puerto (uvicorn sí lo setea), lo que haría que esta
    detección dijera "puerto libre" con uvicorn ya corriendo. Un bind+close
    limpio no deja TIME_WAIT, así que no bloquea el arranque posterior.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def _run_backend() -> None:
    uvicorn.run(
        "backend.api.main:app",
        host="127.0.0.1",
        port=_backend_port(),
        log_level="warning",
        reload=False,
    )


def _ensure_backend(timeout: float = 10.0) -> None:
    """Arranca el backend una sola vez; no-op si ya está corriendo."""
    global _backend_started
    with _backend_lock:
        if _backend_started:
            return
        _backend_started = True

        port = _backend_port()
        if _port_in_use(port):
            logger.info(
                "Puerto %s ya ocupado — asumimos uvicorn local corriendo y no "
                "arrancamos un segundo backend.", port,
            )
            return

        logger.info("Arrancando backend de FastAPI en el puerto %s (hilo daemon)...", port)
        threading.Thread(
            target=_run_backend,
            name="docuguard-backend",
            daemon=True,
        ).start()

        # Esperamos a que el hilo haya bindeado el puerto para que el health
        # check de la primera carga no pegue contra un backend todavía dormido.
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _port_in_use(port):
                return
            time.sleep(0.2)


st.set_page_config(
    page_title="DocuGuard AI Lite",
    page_icon="",
    layout="wide",
)

st.title("DocuGuard AI Lite")
st.markdown("Verificación de cumplimiento documental con IA multi-agente")

# Aseguramos que el backend esté corriendo antes del health check. En
# Streamlit Community Cloud este es el único momento en que el backend puede
# arrancar (no hay uvicorn manual); localmente es un no-op si ya está levantado.
_ensure_backend()

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

# --- Cooldown check --------------------------------------------------------
cooldown_remaining = _cooldown_remaining()
in_cooldown = cooldown_remaining > 0

# El botón "Ver reporte" se evalúa ACÁ, antes que nada del cooldown y del
# auto-redirect. Motivo: si estuviera después del bloque de cooldown, un click
# en este botón mientras el cooldown está activo nunca llegaría a ejecutarse,
# porque el cooldown corta el script con su propio st.rerun() antes de llegar
# hasta acá. Y si estuviera después del auto-redirect, un click no podría
# ganarle al timer: el switch_page de acá corta la ejecución antes de que el
# timer se evalúe, evitando doble navegación.
if st.session_state.get("last_uploaded_doc_id"):
    if st.button("Ver reporte", key="ver_reporte_btn"):
        _goto_reportes()

# Mensajes del último upload persistidos en session_state. Los st.success /
# st.info transitorios se borran con cada rerun, así que si los mostráramos
# directo desaparecerían al instante durante las vueltas del auto-redirect.
if st.session_state.get("upload_success_msg"):
    st.success(st.session_state["upload_success_msg"])
if st.session_state.get("upload_info_msg"):
    st.info(st.session_state["upload_info_msg"])

# --- Auto-redirect a Reportes ----------------------------------------------
# Después de un upload exitoso navegamos solo a Reportes en ~2 segundos, salvo
# que la persona clickee "Ver reporte" antes. Como el botón se evalúa ARRIBA de
# este bloque, un click siempre gana contra el timer: en la corrida donde hay
# click, switch_page corta la ejecución antes de llegar hasta acá.
auto_redirect_until = st.session_state.get("auto_redirect_until")
if auto_redirect_until is not None:
    if time.time() >= auto_redirect_until:
        _goto_reportes()
    else:
        # Cuenta regresiva con el mismo patrón del cooldown: sleep corto +
        # rerun, revisando en cada vuelta si ya pasaron los 2 segundos o si la
        # persona clickeó "Ver reporte" en el medio de una vuelta.
        time.sleep(0.5)
        st.rerun()

col1, col2 = st.columns([3, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Seleccionar archivo",
        type=["pdf", "png", "jpg", "jpeg", "txt"],
        label_visibility="collapsed",
        disabled=in_cooldown,
    )

with col2:
    st.markdown("### ")
    process_btn = st.button(
        "Procesar",
        type="primary",
        disabled=not (uploaded_file and api_ok) or in_cooldown,
    )

if in_cooldown:
    st.info(
        f"Podés subir otro documento en {int(cooldown_remaining) + 1} segundos."
    )
    # Refresca la página cada segundo mientras dure el cooldown, para que
    # la cuenta regresiva se actualice sola sin que la persona haga nada.
    time.sleep(1)
    st.rerun()

if process_btn and uploaded_file and api_ok and not in_cooldown:
    with st.spinner("Subiendo documento..."):
        files = {"file": (uploaded_file.name, uploaded_file.read(), uploaded_file.type)}
        try:
            r = httpx.post(_api_url("documents/upload"), files=files, timeout=30)
        except Exception as e:
            st.error(f"No se pudo conectar al backend: {e}")
            r = None

        if r is not None and r.status_code == 200:
            data = r.json()
            doc_id = data["doc_id"]
            st.session_state["last_upload_time"] = time.time()
            st.session_state["last_uploaded_doc_id"] = doc_id
            # El cooldown lo maneja el backend (record_upload), que fue quien
            # procesó el upload. El frontend no persiste nada: en el próximo
            # _cooldown_remaining() va a consultar GET /documents/cooldown y
            # recibirá el cooldown activo. Ya no hay cookie que escribir.
            # Arrancamos el timer de auto-redirect a Reportes (~2 segundos).
            st.session_state["auto_redirect_until"] = time.time() + AUTO_REDIRECT_SECONDS
            st.session_state["upload_success_msg"] = f"Documento subido exitosamente. ID: {doc_id}"
            st.session_state["upload_info_msg"] = (
                "El procesamiento está corriendo en segundo plano. "
                "Te llevamos a Reportes en unos segundos, "
                "o usá el botón 'Ver reporte' para ir ahora mismo."
            )
            # Rerun inmediato para que el bloque de auto-redirect tome el timer.
            # Sin esto, la página quedaría esperando interacción y el timer del
            # auto-redirect nunca llegaría a evaluarse (no habría navegación).
            st.rerun()
        elif r is not None:
            if r.status_code == 429:
                st.error(
                    "El backend rechazó el upload por límite de cooldown/cuota. "
                    f"Detalle: {r.text}"
                )
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
