"""Extractor Agent: extracts structured fields from document text."""
from typing import Optional

from backend.llm.router import call_llm
from backend.agents.state import AgentState, ExtractedInfo


EXTRACTOR_SYSTEM_PROMPT = """Eres un extractor de datos documentales. Tu tarea es analizar el texto de un documento legal o comercial y extraer la información estructurada solicitada.

Debes devolver exclusivamente un JSON con esta estructura:
{
  "doc_type": "contract|nda|invoice|unknown",
  "parties": ["nombre parte 1", "nombre parte 2"],
  "dates": {"fecha_contrato": "..." , "fecha_inicio": "...", "fecha_terminacion": "...", "fecha_vencimiento": "..."},
  "amounts": {"moneda": "USD|ARS|EUR", "monto_total": 0.0, "iva": 0.0, "subtotal": 0.0},
  "clauses": {
    "terminacion": "texto de la clausula o null si no existe",
    "penalizacion": "texto de la clausula o null si no existe",
    "jurisdiccion": "texto de la clausula o null si no existe",
    "confidencialidad": "texto de la clausula o null si no existe",
    "proteccion_datos": "texto de la clausula o null si no existe"
  },
  "campos_ausentes": ["lista", "de", "campos", "obligatorios", "que", "faltan"]
}

Responde SOLO con el JSON, sin explicaciones adicionales."""


async def extractor_agent(state: AgentState) -> dict:
    """Extract structured information from document text."""
    doc_id = state["doc_id"]
    raw_text = state["raw_text"]

    if not raw_text or len(raw_text.strip()) < 20:
        return {"errors": [f"Document {doc_id} has insufficient text for extraction"]}

    try:
        response = await call_llm(
            prompt=f"Documento a analizar:\n\n{raw_text[:8000]}",
            system=EXTRACTOR_SYSTEM_PROMPT,
            task_type="extraction",
            agent_name="extractor",
            doc_id=doc_id,
            temperature=0.0,
            max_tokens=2000,
        )
    except Exception as e:
        return {"errors": [f"Extractor LLM call failed: {e}"]}

    # Parse JSON from response
    import json, re
    extracted: Optional[ExtractedInfo] = None
    try:
        json_str = response.strip()
        match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if match:
            json_str = match.group(0)
        extracted = json.loads(json_str)
    except (json.JSONDecodeError, IndexError) as e:
        return {"errors": [f"Failed to parse extractor output as JSON: {e}", f"Raw output: {response[:500]}"]}

    # Detect doc_type from document text if not provided by LLM
    doc_type = (extracted or {}).get("doc_type", "unknown")
    if doc_type == "unknown":
        text_lower = raw_text.lower()
        if any(w in text_lower for w in ["factura", "facturación", "facturacion", "iva", "subtotal"]):
            doc_type = "invoice"
        elif any(w in text_lower for w in ["confidencialidad", "nda", "acuerdo de confidencialidad"]):
            doc_type = "nda"
        elif any(w in text_lower for w in ["contrato", "cláusula", "clausula", "servicios"]):
            doc_type = "contract"

    return {
        "extracted_info": extracted,
        "doc_type": doc_type,
    }
