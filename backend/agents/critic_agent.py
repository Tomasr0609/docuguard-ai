"""Critic Agent: classifies severity of each finding (zero-shot)."""
import logging

from backend.llm.router import call_llm
from backend.agents.state import AgentState

logger = logging.getLogger(__name__)


CRITIC_SYSTEM_PROMPT = f"""Eres un clasificador de riesgos documentales. Para cada hallazgo detectado, debes asignar una severidad y un score de riesgo.

Clasifica cada hallazgo como:
- "high": riesgo significativo, probable incumplimiento regulatorio o pérdida financiera material
- "medium": riesgo moderado, desviación del estándar que podría tener consecuencias
- "low": riesgo menor, desviación leve o ambigua, tecnicismo

Reglas:
- Penalizaciones > 5% mensual sin tope -> high
- Intereses moratorios > 3% mensual -> medium
- Ausencia de cláusula de terminación -> high
- Jurisdicción atípica pero presente -> low
- Confidencialidad perpetua -> high
- Omisión de exclusiones estándar en NDA -> medium
- Inconsistencia en montos de factura -> high
- Omisión de campos obligatorios en factura -> medium
- No más del 50% de los hallazgos deben ser "high"

IMPORTANTE: El campo "type" de cada objeto DEBE ser EXACTAMENTE el mismo
que aparece en el hallazgo de entrada. No lo modifiques, no lo traduzcas,
no le agregues prefijos ni sufijos. Conservalo literal.

Responde SOLO con un JSON array de objetos:
[
  {{
    "type": "type_exacto_del_hallazgo",
    "severity": "high|medium|low",
    "risk_score": 0.0-1.0
  }}
]"""


async def critic_agent(state: AgentState) -> dict:
    """Classify severity of each finding."""
    doc_id = state["doc_id"]
    findings = state.get("findings", [])

    if not findings:
        return {"risk_level": "none", "risk_score": 0.0}

    findings_json = __import__("json").dumps(findings, ensure_ascii=False, indent=2)

    prompt = f"Clasifica la severidad de estos hallazgos:\n\n{findings_json}"

    try:
        response = await call_llm(
            prompt=prompt,
            system=CRITIC_SYSTEM_PROMPT,
            task_type="classification",
            agent_name="critic",
            doc_id=doc_id,
            temperature=0.1,
            max_tokens=2000,
        )
    except Exception as e:
        return {"errors": [f"Critic LLM call failed: {e}"]}

    # Parse JSON array from response
    import json, re
    classified = []
    try:
        json_str = response.strip()
        match = re.search(r'\[.*\]', json_str, re.DOTALL)
        if match:
            json_str = match.group(0)
        classified = json.loads(json_str)
        if not isinstance(classified, list):
            classified = []
        logger.info("critic parsed response for doc_id=%s: %s", doc_id, classified)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(
            "critic JSON parse FAILED for doc_id=%s. Raw response (first 2000 chars): %r",
            doc_id, response[:2000],
        )
        return {"errors": [f"Failed to parse critic output: {e}"]}

    # Merge severity back into findings
    severity_by_type = {c["type"]: c for c in classified if "type" in c and "severity" in c}

    updated_findings = []
    for f in findings:
        enriched = dict(f)
        ft = f.get("type", "")
        if ft in severity_by_type:
            enriched["severity"] = severity_by_type[ft]["severity"]
            enriched["risk_score"] = severity_by_type[ft].get("risk_score", 0.5)
        else:
            enriched["severity"] = "medium"
            enriched["risk_score"] = 0.5
        updated_findings.append(enriched)

    # Determine overall risk level
    severities = [f.get("severity", "low") for f in updated_findings]
    if "high" in severities:
        risk_level = "high"
    elif "medium" in severities:
        risk_level = "medium"
    else:
        risk_level = "low"

    risk_scores = [f.get("risk_score", 0.5) for f in updated_findings]
    risk_score = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0

    return {
        "findings": updated_findings,
        "risk_level": risk_level,
        "risk_score": risk_score,
    }
