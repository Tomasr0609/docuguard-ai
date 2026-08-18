"""Verifier Agent: compares document against corpus normativo via RAG."""
import logging

from backend.llm.router import call_llm
from backend.rag.retriever import retrieve_context
from backend.agents.state import AgentState, FINDING_TYPE_TAXONOMY

logger = logging.getLogger(__name__)

_TAXONOMY_LINE = "\n".join(f"  - {t}" for t in FINDING_TYPE_TAXONOMY)

_VALID_TYPES_BY_DOC_TYPE: dict[str, set[str]] = {
    "nda": {"missing_jurisdiction", "missing_standard_exclusions", "no_data_protection",
            "overbroad_confidentiality", "perpetual_confidentiality", "unusual_jurisdiction"},
    "contract": {"excessive_interest", "missing_jurisdiction", "missing_termination_clause",
                 "missing_termination_notice", "no_cap_liability", "no_data_protection",
                 "penalty_ambiguous", "unfavorable_penalty", "unusual_jurisdiction"},
    "invoice": {"amount_inconsistency", "missing_required_fields"},
}

# Keywords por tipo de finding, usadas tanto para construir la query RAG
# (Fix de recall) como para el filtro de coherencia temática. Vive a nivel de
# módulo para no duplicarla entre ambas funciones.
_TYPE_KEYWORDS: dict[str, list[str]] = {
    "amount_inconsistency": ["monto", "total", "subtotal", "iva", "factura", "cobro", "precio"],
    "excessive_interest": ["interes", "moratorio", "tasa", "mensual"],
    "missing_jurisdiction": ["jurisdiccion", "tribunal", "legal", "litigio", "ley"],
    "missing_required_fields": ["falta", "requisito", "campo", "obligatorio"],
    "missing_standard_exclusions": ["exclusion", "excluye", "exceptua", "no aplica"],
    "missing_termination_clause": ["terminacion", "rescicion", "cancelacion", "finalizacion"],
    "missing_termination_notice": ["notificacion", "preaviso", "aviso", "notificar"],
    "no_cap_liability": ["responsabilidad", "limite", "maximo", "tope", "indemnizacion"],
    "no_data_protection": ["datos", "proteccion", "privacidad", "gdpr", "personal"],
    "overbroad_confidentiality": ["confidencial", "secreto", "divulgacion"],
    "penalty_ambiguous": ["penalizacion", "sancion", "mora", "ambiguo", "penal",
                          "criterio", "discrecion", "unilateral", "interes"],
    "perpetual_confidentiality": ["confidencial", "perpetuo", "indefinido", "permanente", "vigencia"],
    "unfavorable_penalty": ["penalizacion", "sancion", "mora", "excesivo", "desproporcionado"],
    "unusual_jurisdiction": ["jurisdiccion", "tribunal", "competencia", "atipico", "inusual"],
}


def _build_rag_query(doc_type: str) -> str:
    """Construye la query de retrieval a partir de los tipos de finding válidos
    para este doc_type, para que el contexto RAG cubra semánticamente todos los
    temas que el verifier podría necesitar evaluar."""
    valid_types = _VALID_TYPES_BY_DOC_TYPE.get(doc_type)
    if not valid_types:
        return "clausulas estandar obligaciones contractuales"

    terms: set[str] = set()
    for t in valid_types:
        terms.update(_TYPE_KEYWORDS.get(t, []))

    if not terms:
        return "clausulas estandar obligaciones contractuales"

    return " ".join(sorted(terms))


VERIFIER_SYSTEM_PROMPT = f"""Eres un verificador de cumplimiento documental. Tu tarea es comparar el texto de un documento contra las cláusulas de referencia (corpus normativo) proporcionadas y detectar desviaciones, riesgos o cláusulas problemáticas.

=== REGLAS DE FUNDAMENTACIÓN (OBLIGATORIAS) ===
- SOLO reportá un hallazgo si podés citar texto EXACTO del documento que lo respalde. Si no hay texto real que lo sustente, NO lo reportes.
- Antes de reportar 'falta X cláusula', releé el documento completo — si la cláusula está presente aunque con otro título o formato, NO es un hallazgo.
- Si el documento no menciona un tema (ej. no hay cláusula de penalización), NO infieras un problema sobre algo que no existe — la ausencia total de un tema no es automáticamente un hallazgo, solo la ausencia de cláusulas que el corpus normativo indica como obligatorias.
- Ante la duda, preferí NO reportar. Es preferible un array vacío a un hallazgo sin fundamento real.
- El source_snippet debe poder encontrarse con Ctrl+F exacto en el documento. Si tenés que resumir o parafrasear para explicar el hallazgo, hacelo en el campo 'description', nunca en 'source_snippet'.

EJEMPLO — documento conforme:
Si el documento incluye todas las cláusulas esperadas correctamente redactadas, respondé: []

PASO DE AUTORREVISIÓN (OBLIGATORIO antes de responder):
Para cada hallazgo que ibas a incluir, verificá:
- ¿La cita que elegiste (source_snippet) realmente demuestra el problema del tipo que estás reportando?
- Si el tipo es 'missing_X' o 'no_X' (algo que FALTA), ¿tu propia cita menciona ese elemento? Si la cita SÍ menciona el elemento que decís que falta, hay una contradicción — eliminá ese hallazgo.
- Si la cita habla de un tema distinto al tipo de hallazgo (ej. citás la cláusula de protección de datos para justificar un hallazgo de penalización), eliminá ese hallazgo — la cita debe ser sobre el mismo tema exacto que el tipo de hallazgo.
Solo incluí en tu respuesta final los hallazgos que pasen esta autorrevisión.

Para cada hallazgo, debes determinar:
1. El tipo de hallazgo (usa EXACTAMENTE uno de los códigos de la taxonomía obligatoria más abajo)
2. Una descripción clara de por qué es problemático
3. El texto EXACTO del documento que respalda el hallazgo (cita textual entre comillas)
4. La cláusula de referencia con la que se compara

=== TAXONOMÍA OBLIGATORIA DE TIPOS DE HALLAZGO ===
Usá SOLO estos códigos en el campo "type". No inventes códigos nuevos:

{_TAXONOMY_LINE}

Responde SOLO con un JSON array. Cada elemento del array debe tener:
{{
  "type": "código_de_la_taxonomía",
  "description": "descripción del problema",
  "source_snippet": "cita textual EXACTA del documento entre comillas",
  "reference_clause": "cláusula de referencia relevante"
}}

Si no encuentras desviaciones, responde con un array vacío [].

NO incluyas explicaciones adicionales fuera del JSON."""


async def verifier_agent(state: AgentState) -> dict:
    """Compare document text against corpus normativo using RAG."""
    doc_id = state["doc_id"]
    raw_text = state["raw_text"]
    _extracted_dt = (state.get("extracted_info") or {}).get("doc_type")
    _filename_dt = state.get("doc_type")
    doc_type = (
        _extracted_dt if _extracted_dt and _extracted_dt != "unknown"
        else (_filename_dt if _filename_dt and _filename_dt != "unknown" else "unknown")
    )
    logger.info("verifier_agent: doc_id=%s usando doc_type=%s (extracted=%s filename=%s)", doc_id, doc_type, _extracted_dt, _filename_dt)

    if not raw_text or len(raw_text.strip()) < 20:
        return {"errors": [f"Document {doc_id} has insufficient text for verification"]}

    # Build a RAG context query from the valid finding types for this doc_type.
    # This guarantees the reference clauses for ALL relevant topics (data
    # protection, liability cap, termination notice, ...) reach the LLM context,
    # instead of a hand-written query that could omit them.
    query = _build_rag_query(doc_type)
    context = retrieve_context(query, k=6, max_chars=5000)

    valid_types_str = ""
    if doc_type in _VALID_TYPES_BY_DOC_TYPE:
        valid_types_str = (
            f"\n\nTIPOS DE HALLAZGO VÁLIDOS PARA {doc_type.upper()}:\n"
            f"{', '.join(sorted(_VALID_TYPES_BY_DOC_TYPE[doc_type]))}\n"
            f"No reportes hallazgos de tipos que no estén en esta lista."
        )

    prompt = (
        f"Tipo de documento: {doc_type}\n\n"
        f"=== TEXTO DEL DOCUMENTO ===\n{raw_text[:6000]}\n\n"
        f"=== CLAUSULAS DE REFERENCIA (CORPUS NORMATIVO) ===\n{context}"
        f"{valid_types_str}\n\n"
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

    # Validate that each finding's source_snippet actually appears in raw_text
    raw_lower = raw_text.lower()
    validated = []
    for f in findings_raw:
        snippet = (f.get("source_snippet") or "").strip()
        if not snippet:
            logger.warning(
                "Hallazgo descartado por falta de source_snippet en doc_id=%s: type=%s",
                doc_id, f.get("type"),
            )
            continue

        # Check direct substring match (case-insensitive)
        if snippet.lower() in raw_lower:
            validated.append(f)
            continue

        # Fallback: check word-level overlap (≥70% of snippet words must appear in raw_text)
        words = [w for w in snippet.lower().split() if len(w) > 3]
        if words:
            match_count = sum(1 for w in words if w in raw_lower)
            coverage = match_count / len(words)
            if coverage >= 0.5:
                validated.append(f)
                continue
            logger.warning(
                "Hallazgo descartado por falta de fundamentación real en doc_id=%s "
                "(coverage=%.2f): type=%s snippet=%r",
                doc_id, coverage, f.get("type"), snippet,
            )
        else:
            validated.append(f)

    # Thematic coherence filter: verify snippet content matches finding type.
    # Uses the module-level _TYPE_KEYWORDS (shared with _build_rag_query).
    coherent = []
    for f in validated:
        ftype = f.get("type", "")
        keywords = _TYPE_KEYWORDS.get(ftype)
        if keywords is None:
            coherent.append(f)
            continue
        snippet = (f.get("source_snippet") or "").lower()
        if not snippet:
            logger.warning(
                "Hallazgo descartado por falta de source_snippet en doc_id=%s: type=%s",
                doc_id, ftype,
            )
            continue
        is_absence_type = (ftype.startswith("missing_") or ftype.startswith("no_")) and ftype != "missing_required_fields"
        if is_absence_type:
            # For absence types, search keywords in the FULL document, not just the snippet.
            # If the topic IS mentioned anywhere in the doc, the finding is contradictory.
            any_in_doc = any(kw in raw_lower for kw in keywords)
            if any_in_doc:
                logger.warning(
                    "Hallazgo descartado por contradicción lógica en doc_id=%s "
                    "type=%s: el documento menciona el tema que debería faltar",
                    doc_id, ftype,
                )
                continue
            coherent.append(f)
        else:
            # For non-absence types, check that the snippet itself is on-topic.
            snippet_lower = snippet.lower()
            any_in_snippet = any(kw in snippet_lower for kw in keywords)
            if not any_in_snippet:
                logger.warning(
                    "Hallazgo descartado por falta de relación temática en doc_id=%s "
                    "type=%s: ningún keyword del tema aparece en snippet=%r",
                    doc_id, ftype, snippet,
                )
                continue
            coherent.append(f)

    # Inject deterministic amount inconsistency finding (flagged by extractor)
    _extr = state.get("extracted_info") or {}
    _flags = _extr.get("_flags", {}) if isinstance(_extr, dict) else {}
    if "amount_inconsistency" in _flags:
        info = _flags["amount_inconsistency"]
        coherent.append({
            "type": "amount_inconsistency",
            "description": (
                f"Inconsistencia de montos: subtotal+IVA ({info['expected']}) "
                f"no coincide con monto_total ({info['actual']}), "
                f"diferencia de {info['difference']}"
            ),
            "source_snippet": "",
            "reference_clause": "Los montos de factura deben ser consistentes",
        })

    # Doc-type validity filter: discard findings whose type never occurs for this doc_type
    doc_type_filtered = []
    valid_for_dt = _VALID_TYPES_BY_DOC_TYPE.get(doc_type)
    for f in coherent:
        if valid_for_dt is None or f.get("type") in valid_for_dt:
            doc_type_filtered.append(f)
        else:
            logger.warning(
                "Hallazgo descartado por tipo no válido para doc_type=%s en doc_id=%s: "
                "type=%s", doc_type, doc_id, f.get("type"),
            )

    # Normalize findings to match state Finding type
    findings = []
    for f in doc_type_filtered:
        findings.append({
            "type": f.get("type", "unknown"),
            "description": f.get("description", ""),
            "source_snippet": f.get("source_snippet"),
            "reference_clause": f.get("reference_clause"),
            "agent_name": "verifier",
        })

    return {"findings": findings}
