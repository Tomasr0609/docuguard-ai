"""Writer Agent: generates executive summary with traceable citations."""
from backend.llm.router import call_llm
from backend.agents.state import AgentState


WRITER_SYSTEM_PROMPT = """Eres un redactor de informes ejecutivos de compliance. Tu tarea es generar un resumen claro y profesional.

El reporte debe incluir:
1. Un párrafo ejecutivo con el nivel de riesgo global
2. Lista numerada de hallazgos, cada uno con:
   - Tipo de hallazgo
   - Severidad (high/medium/low)
   - Descripción del problema
   - Cita textual del documento original (entre comillas)
   - Referencia a la cláusula estándar con la que se compara
3. Recomendaciones accionables (2-3)

Redacción formal y profesional. Usa el tipo de documento (contrato/NDA/factura) en la redacción.

Responde SOLO con el texto del reporte, sin JSON."""


async def writer_agent(state: AgentState) -> dict:
    """Generate executive summary from findings."""
    doc_id = state["doc_id"]
    raw_text = state["raw_text"]
    findings = state.get("findings", [])
    risk_level = state.get("risk_level", "none")
    risk_score = state.get("risk_score", 0.0)
    extracted = state.get("extracted_info") or {}
    doc_type = extracted.get("doc_type", "documento")

    findings_text = __import__("json").dumps(findings, ensure_ascii=False, indent=2)

    prompt = (
        f"Tipo de documento: {doc_type}\n"
        f"Document ID: {doc_id}\n"
        f"Riesgo global: {risk_level} (score: {risk_score})\n\n"
        f"=== HALLAZGOS ===\n{findings_text}\n\n"
        f"=== TEXTO ORIGINAL (primeros 3000 caracteres) ===\n{raw_text[:3000]}\n\n"
        f"Genera el reporte ejecutivo."
    )

    try:
        summary = await call_llm(
            prompt=prompt,
            system=WRITER_SYSTEM_PROMPT,
            task_type="writing",
            agent_name="writer",
            doc_id=doc_id,
            temperature=0.3,
            max_tokens=3000,
        )
    except Exception as e:
        return {"errors": [f"Writer LLM call failed: {e}"]}

    return {"executive_summary": summary}
