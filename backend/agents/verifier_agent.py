"""Verifier Agent: compares document against corpus normativo via RAG."""
from backend.llm.router import call_llm
from backend.rag.retriever import retrieve_context
from backend.agents.state import AgentState, FINDING_TYPE_TAXONOMY

_TAXONOMY_LINE = "\n".join(f"  - {t}" for t in FINDING_TYPE_TAXONOMY)

VERIFIER_SYSTEM_PROMPT = f"""Eres un verificador de cumplimiento documental. Tu tarea es comparar el texto de un documento contra las cláusulas de referencia (corpus normativo) proporcionadas y detectar desviaciones, riesgos o cláusulas problemáticas.

Para cada hallazgo, debes determinar:
1. El tipo de hallazgo (usa EXACTAMENTE uno de los códigos de la taxonomía obligatoria más abajo)
2. Una descripción clara de por qué es problemático
3. El texto exacto del documento que respalda el hallazgo (cita textual)
4. La cláusula de referencia con la que se compara

=== TAXONOMÍA OBLIGATORIA DE TIPOS DE HALLAZGO ===
Usá SOLO estos códigos en el campo "type". No inventes códigos nuevos:

{_TAXONOMY_LINE}

Responde SOLO con un JSON array. Cada elemento del array debe tener:
{{
  "type": "código_de_la_taxonomía",
  "description": "descripción del problema",
  "source_snippet": "cita textual del documento",
  "reference_clause": "cláusula de referencia relevante"
}}

Si no encuentras desviaciones, responde con un array vacío [].

NO incluyas explicaciones adicionales fuera del JSON."""


async def verifier_agent(state: AgentState) -> dict:
    """Compare document text against corpus normativo using RAG."""
    doc_id = state["doc_id"]
    raw_text = state["raw_text"]
    doc_type = (state.get("extracted_info") or {}).get("doc_type", "unknown")

    if not raw_text or len(raw_text.strip()) < 20:
        return {"errors": [f"Document {doc_id} has insufficient text for verification"]}

    # Build a RAG context query based on the document type
    query_hints = {
        "contract": "clausula de terminacion penalizacion jurisdiccion incumplimiento",
        "nda": "confidencialidad periodo vigencia exclusiones informacion",
        "invoice": "factura requisitos iva subtotal total datos obligatorios",
        "unknown": "clausulas estandar obligaciones contractuales",
    }
    query = query_hints.get(doc_type, query_hints["unknown"])
    context = retrieve_context(query, k=4, max_chars=4000)

    prompt = (
        f"Tipo de documento: {doc_type}\n\n"
        f"=== TEXTO DEL DOCUMENTO ===\n{raw_text[:6000]}\n\n"
        f"=== CLAUSULAS DE REFERENCIA (CORPUS NORMATIVO) ===\n{context}\n\n"
        f"Compara el documento contra las cláusulas de referencia. "
        f"Identifica cualquier desviación, riesgo o cláusula problemática."
    )

    try:
        response = await call_llm(
            prompt=prompt,
            system=VERIFIER_SYSTEM_PROMPT,
            task_type="verification",
            agent_name="verifier",
            doc_id=doc_id,
            temperature=0.0,
            max_tokens=3000,
        )
    except Exception as e:
        return {"errors": [f"Verifier LLM call failed: {e}"]}

    # Parse JSON array from response
    import json, re
    findings_raw: list[dict] = []
    try:
        json_str = response.strip()
        match = re.search(r'\[.*\]', json_str, re.DOTALL)
        if match:
            json_str = match.group(0)
        try:
            findings_raw = json.loads(json_str)
        except json.JSONDecodeError:
            from json_repair import repair_json
            findings_raw = json.loads(repair_json(json_str))
        if not isinstance(findings_raw, list):
            findings_raw = []
    except (json.JSONDecodeError, IndexError) as e:
        return {"errors": [f"Failed to parse verifier output: {e}"]}

    # Normalize findings to match state Finding type
    findings = []
    for f in findings_raw:
        findings.append({
            "type": f.get("type", "unknown"),
            "description": f.get("description", ""),
            "source_snippet": f.get("source_snippet"),
            "reference_clause": f.get("reference_clause"),
            "agent_name": "verifier",
        })

    return {"findings": findings}
