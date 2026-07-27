"""Generate synthetic dataset for DocuGuard AI Lite evaluation.

Distribution:
- 40 docs total: 40% clean (16), 60% with findings (24)
- 3 types: contract, nda, invoice (roughly even)
- Each doc in 3 formats: .txt, .pdf, .png
- Severity: no more than 50% of findings are high
- 2-3 intentionally ambiguous cases
- Invoice totals calculated programmatically
"""
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Optional

import fitz
from PIL import Image, ImageDraw, ImageFilter

random.seed(42)

# ---- Config ----
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic_docs"
GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "ground_truth.jsonl"
NUM_DOCS = 40
CLEAN_RATIO = 0.4

DOC_TYPES = ["contract", "nda", "invoice"]
DOC_TYPES_WEIGHTS = [0.4, 0.3, 0.3]  # ~16 contracts, ~12 ndas, ~12 invoices

# ---- Document Templates ----

CONTRACT_TEMPLATES = [
    {
        "name": "Contrato de Servicios de Consultoría",
        "parties": ("Consultora TechSolutions S.A.", "Empresa Cliente {client_num} S.R.L."),
        "scope": "Servicios de consultoría en transformación digital, incluyendo análisis de procesos, implementación de sistemas ERP, y capacitación de personal.",
        "duration_days": (180, 365),
        "amount": (25000, 150000),
        "currency": "USD",
    },
    {
        "name": "Contrato de Mantenimiento de Infraestructura TI",
        "parties": ("InfraServe S.A.", "Organización Cliente {client_num} S.A."),
        "scope": "Servicios de mantenimiento preventivo y correctivo de infraestructura tecnológica, incluyendo servidores, redes y equipamiento de usuario final.",
        "duration_days": (365, 730),
        "amount": (50000, 200000),
        "currency": "USD",
    },
    {
        "name": "Contrato de Desarrollo de Software",
        "parties": ("DevFactory S.A.S.", "Empresa Adquirente {client_num} S.A."),
        "scope": "Desarrollo de plataforma web para gestión de inventarios, incluyendo backend, frontend, base de datos, y despliegue en cloud.",
        "duration_days": (90, 180),
        "amount": (80000, 300000),
        "currency": "USD",
    },
    {
        "name": "Contrato de Servicios de Marketing Digital",
        "parties": ("MarketPro Agencia Digital S.L.", "Comitente {client_num} S.A."),
        "scope": "Servicios integrales de marketing digital: gestión de redes sociales, campañas SEM, SEO, email marketing, y generación de contenido.",
        "duration_days": (90, 180),
        "amount": (15000, 60000),
        "currency": "USD",
    },
]

NDA_TEMPLATES = [
    {
        "name": "Acuerdo de Confidencialidad Unilateral",
        "disclosing": "InnovateCorp {client_num} S.A.",
        "receiving": "Proveedor Tecnológico Asociado {client_num} S.L.",
        "purpose": "Evaluación de posible colaboración en desarrollo de producto",
        "term_years": (2, 5),
    },
    {
        "name": "Acuerdo de Confidencialidad Recíproco",
        "parties": ("Biotec Labs {client_num} S.A.", "PharmaPartner {client_num} S.L."),
        "purpose": "Joint venture para investigación y desarrollo de nuevos fármacos",
        "term_years": (3, 5),
    },
    {
        "name": "NDA para Due Diligence",
        "disclosing": "TargetCompany {client_num} S.A.",
        "receiving": "Potential Acquirer {client_num} Corp.",
        "purpose": "Proceso de due diligence para potencial adquisición",
        "term_years": (2, 3),
    },
]

INVOICE_TEMPLATES = [
    {
        "items": [
            ("Servicio de consultoría - mes {month}", 1, (5000, 15000)),
            ("Horas de desarrollo backend", (20, 80), (80, 150)),
            ("Horas de desarrollo frontend", (20, 60), (75, 130)),
            ("Licencia de software - período mensual", 1, (1000, 5000)),
        ],
        "vat_rate": 0.21,
    },
    {
        "items": [
            ("Servicio de mantenimiento mensual", 1, (3000, 10000)),
            ("Horas de soporte técnico", (10, 40), (60, 120)),
            ("Infraestructura cloud - consumo mensual", 1, (2000, 8000)),
            ("Capacitación in company", (1, 3), (2000, 5000)),
        ],
        "vat_rate": 0.21,
    },
    {
        "items": [
            ("Campaña SEM - Google Ads", 1, (2000, 10000)),
            ("Creación de contenido - artículos", (4, 12), (200, 500)),
            ("Gestión de redes sociales - mensual", 1, (1500, 4000)),
            ("Reporte de métricas y análisis", 1, (500, 2000)),
        ],
        "vat_rate": 0.21,
    },
]

# ---- Risk Findings Configuration ----

FINDINGS_DEFS = [
    {
        "type": "missing_termination_clause",
        "severity": "high",
        "description": "El contrato no incluye una cláusula de terminación anticipada con períodos de notificación y cura.",
    },
    {
        "type": "unfavorable_penalty",
        "severity": "high",
        "description": "La penalización por incumplimiento es del 10% mensual sobre el valor del contrato, excesiva y sin tope máximo.",
    },
    {
        "type": "excessive_interest",
        "severity": "medium",
        "description": "El interés moratorio del 5% mensual excede el estándar de mercado de 1-2% mensual.",
    },
    {
        "type": "missing_jurisdiction",
        "severity": "medium",
        "description": "No se especifica la ley aplicable ni la jurisdicción para resolver controversias.",
    },
    {
        "type": "unusual_jurisdiction",
        "severity": "low",
        "description": "La jurisdicción elegida (Tribunales de Islas Caimán) es atípica para un contrato entre partes locales.",
    },
    {
        "type": "no_cap_liability",
        "severity": "high",
        "description": "No existe un límite máximo de responsabilidad (cap), exponiendo a las partes a responsabilidad ilimitada.",
    },
    {
        "type": "overbroad_confidentiality",
        "severity": "medium",
        "description": "La definición de Información Confidencial es excesivamente amplia, sin exclusiones razonables.",
    },
    {
        "type": "perpetual_confidentiality",
        "severity": "high",
        "description": "La obligación de confidencialidad tiene duración perpetua, excediendo el estándar de 2-5 años.",
    },
    {
        "type": "missing_standard_exclusions",
        "severity": "medium",
        "description": "El NDA no incluye las exclusiones estándar de información pública o desarrollada independientemente.",
    },
    {
        "type": "amount_inconsistency",
        "severity": "high",
        "description": "El total de la factura no coincide con la suma de los ítems más IVA.",
    },
    {
        "type": "missing_required_fields",
        "severity": "medium",
        "description": "La factura carece de campos obligatorios como número de factura, fecha de vencimiento, o datos fiscales completos.",
    },
    {
        "type": "missing_termination_notice",
        "severity": "low",
        "description": "La cláusula de terminación no especifica un período mínimo de notificación para terminación sin causa.",
    },
    {
        "type": "penalty_ambiguous",
        "severity": "low",
        "description": "La penalización del 3% mensual está en el límite de lo considerado estándar, y su redacción es ambigua.",
    },
    {
        "type": "no_data_protection",
        "severity": "high",
        "description": "El contrato no incluye cláusula de protección de datos personales conforme a GDPR.",
    },
]

# which finding types apply per doc_type
FINDINGS_BY_DOCTYPE = {
    "contract": [f for f in FINDINGS_DEFS if f["type"] in (
        "missing_termination_clause", "unfavorable_penalty", "excessive_interest",
        "missing_jurisdiction", "unusual_jurisdiction", "no_cap_liability",
        "no_data_protection", "missing_termination_notice", "penalty_ambiguous",
    )],
    "nda": [f for f in FINDINGS_DEFS if f["type"] in (
        "overbroad_confidentiality", "perpetual_confidentiality",
        "missing_standard_exclusions", "missing_jurisdiction",
        "unusual_jurisdiction", "no_data_protection",
    )],
    "invoice": [f for f in FINDINGS_DEFS if f["type"] in (
        "amount_inconsistency", "missing_required_fields",
    )],
}

# ---- Ambiguous cases ----
AMBIGUOUS_FINDING_TYPES = {"penalty_ambiguous", "unusual_jurisdiction", "overbroad_confidentiality"}

AMBIGUOUS_SPECS = [
    {
        "doc_type": "contract",
        "finding": "penalty_ambiguous",
        "detail": "Penalización del 3% mensual con redacción ambigua sobre si se aplica sobre el valor del contrato o sobre la factura impaga.",
    },
    {
        "doc_type": "contract",
        "finding": "unusual_jurisdiction",
        "detail": "Jurisdicción en Islas Caimán para un contrato entre dos empresas argentinas.",
    },
    {
        "doc_type": "nda",
        "finding": "overbroad_confidentiality",
        "detail": "Confidencialidad de 5 años que, aunque dentro del estándar, la definición es tan amplia que incluye 'toda información intercambiada oralmente'.",
    },
]


def build_contract_text(template: dict, client_num: int, findings: list[dict]) -> str:
    t = template
    parties = tuple(p.format(client_num=client_num) for p in t["parties"])
    amount = random.randint(*t["amount"])
    duration = random.randint(*t["duration_days"])
    currency = t["currency"]

    has_termination = True
    has_penalty = True
    has_jurisdiction = True
    has_cap = True
    has_dataprotection = True
    penalty_pct = random.choice([1.0, 1.5, 2.0])
    interest_pct = random.choice([1.0, 1.5, 2.0])
    jurisdiction_place = "Ciudad Autónoma de Buenos Aires"
    penalty_ambiguous_text = ""
    unusual_jurisdiction_text = ""

    for f in findings:
        ft = f["type"]
        if ft == "missing_termination_clause":
            has_termination = False
        elif ft == "unfavorable_penalty":
            penalty_pct = 10.0
        elif ft == "excessive_interest":
            interest_pct = 5.0
        elif ft == "missing_jurisdiction":
            has_jurisdiction = False
        elif ft == "unusual_jurisdiction":
            jurisdiction_place = "Islas Caimán"
        elif ft == "no_cap_liability":
            has_cap = False
        elif ft == "no_data_protection":
            has_dataprotection = False
        elif ft == "penalty_ambiguous":
            penalty_pct = 3.0
            penalty_ambiguous_text = (
                "En caso de mora, se aplicará un interés del 3% mensual sobre las cantidades adeudadas. "
                "Dicho interés podrá ser ajustado periódicamente a criterio del contratista."
            )

    lines = [f"{t['name']}"]
    lines.append(f"Entre {parties[0]} y {parties[1]}")
    lines.append(f"Fecha: {random.choice(['15', '22', '03'])} de {random.choice(['enero', 'marzo', 'junio', 'septiembre'])} de 2025")
    lines.append("")
    lines.append("CLÁUSULA PRIMERA: OBJETO")
    lines.append(t["scope"])
    lines.append("")
    lines.append(f"CLÁUSULA SEGUNDA: PLAZO")
    lines.append(f"El presente contrato tendrá una duración de {duration} días contados desde su firma.")
    lines.append("")
    lines.append(f"CLÁUSULA TERCERA: PRECIO")
    lines.append(f"El contratista percibirá por sus servicios la suma de {currency} {amount:,.2f} pagaderos de la siguiente forma: 50% a la firma y 50% contra entrega de los entregables.")
    lines.append("")

    if has_termination:
        lines.append("CLÁUSULA CUARTA: TERMINACIÓN ANTICIPADA")
        lines.append("Cualquiera de las partes podrá resolver el contrato sin causa mediante preaviso escrito de 30 días calendario. En caso de incumplimiento, la parte incumplidora dispondrá de 15 días hábiles para subsanarlo.")
        lines.append("")
    else:
        lines.append("(El contrato no incluye cláusula de terminación anticipada)")
        lines.append("")

    lines.append("CLÁUSULA QUINTA: PENALIZACIONES")
    penalty_text = penalty_ambiguous_text if penalty_ambiguous_text else (
        f"En caso de incumplimiento, la parte incumplidora abonará a la otra una penalización del {penalty_pct:.1f}% mensual sobre el valor del contrato. "
        f"Se aplicarán intereses moratorios del {interest_pct:.1f}% mensual sobre las sumas adeudadas."
    )
    if has_cap:
        penalty_text += f" La responsabilidad máxima acumulada de cada parte no excederá el 50% del valor del contrato."
    lines.append(penalty_text)
    lines.append("")

    if has_jurisdiction:
        lines.append(f"CLÁUSULA SEXTA: JURISDICCIÓN")
        lines.append(f"Las partes se someten a la jurisdicción de los Tribunales Ordinarios de {jurisdiction_place}, renunciando a cualquier otro fuero o jurisdicción.")
        lines.append("")

    if has_dataprotection:
        lines.append("CLÁUSULA SÉPTIMA: PROTECCIÓN DE DATOS")
        lines.append("Las partes se comprometen a tratar los datos personales conforme a la Ley de Protección de Datos Personales, garantizando el consentimiento, finalidad, proporcionalidad y seguridad de los datos.")
        lines.append("")

    lines.append("CLÁUSULA FINAL: FUERZA MAYOR")
    lines.append("Ninguna parte será responsable por incumplimiento debido a eventos de fuerza mayor debidamente acreditados.")
    lines.append("")
    lines.append(f"Firmado en {jurisdiction_place}, a los {random.randint(1, 28)} días del mes de {random.choice(['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio'])} de 2025.")
    lines.append("")
    lines.append(f"{parties[0]}                                  {parties[1]}")

    return "\n".join(lines)


def build_nda_text(template: dict, client_num: int, findings: list[dict]) -> str:
    t = template
    is_reciprocal = "parties" in t
    if is_reciprocal:
        p1, p2 = tuple(p.format(client_num=client_num) for p in t["parties"])
        disclosing = p1
        receiving = p2
    else:
        disclosing = t["disclosing"].format(client_num=client_num)
        receiving = t["receiving"].format(client_num=client_num)
    purpose = t["purpose"]
    term = random.randint(*t["term_years"])

    has_overbroad = any(f["type"] == "overbroad_confidentiality" for f in findings)
    has_perpetual = any(f["type"] == "perpetual_confidentiality" for f in findings)
    has_missing_exclusions = any(f["type"] == "missing_standard_exclusions" for f in findings)
    has_jurisdiction = not any(f["type"] == "missing_jurisdiction" for f in findings)
    unusual_juris = any(f["type"] == "unusual_jurisdiction" for f in findings)
    has_dataprotection = not any(f["type"] == "no_data_protection" for f in findings)

    lines = [f"Acuerdo de Confidencialidad - {t.get('name', 'NDA')}"]
    lines.append(f"Entre {disclosing} (\"Parte Divulgante\") y {receiving} (\"Parte Receptora\")")
    lines.append(f"Fecha: {random.choice(['10', '18', '25'])} de {random.choice(['enero', 'febrero', 'abril', 'mayo', 'julio'])} de 2025")
    lines.append("")
    lines.append("1. PROPÓSITO")
    lines.append(purpose)
    lines.append("")

    lines.append("2. DEFINICIÓN DE INFORMACIÓN CONFIDENCIAL")
    if has_overbroad:
        lines.append("Se considera Información Confidencial toda información intercambiada entre las partes, incluyendo pero no limitándose a: datos técnicos, financieros, comerciales, know-how, estrategias de negocio, información oral presentada en reuniones, prototipos, especificaciones, y cualquier otro dato que una parte considere confidencial aunque no esté marcado como tal.")
    else:
        lines.append("Se considera Información Confidencial aquella información técnica, financiera o comercial que sea (a) marcada como confidencial al momento de la divulgación, o (b) comunicada oralmente y confirmada por escrito dentro de los 15 días siguientes.")
    lines.append("")

    if not has_missing_exclusions:
        lines.append("3. EXCLUSIONES")
        lines.append("No se considerará Información Confidencial aquella que: (a) sea o se vuelva pública sin violación del presente acuerdo; (b) la Parte Receptora pueda demostrar que conocía previamente; (c) sea recibida de un tercero sin obligación de confidencialidad; (d) sea desarrollada independientemente por la Parte Receptora.")
        lines.append("")

    lines.append("4. OBLIGACIONES DE CONFIDENCIALIDAD")
    lines.append("La Parte Receptora se obliga a: ejercer el mismo grado de cuidado que con su propia información confidencial, limitar el acceso a personal que necesite conocerla, y notificar inmediatamente cualquier divulgación no autorizada.")
    lines.append("")

    lines.append("5. PLAZO DE VIGENCIA")
    if has_perpetual:
        lines.append("Las obligaciones de confidencialidad establecidas en el presente acuerdo se mantendrán vigentes de forma indefinida, incluso después de la terminación del acuerdo.")
    else:
        lines.append(f"Las obligaciones de confidencialidad se mantendrán vigentes por un período de {term} años desde la fecha de divulgación de la información.")
    lines.append("")

    lines.append("6. DEVOLUCIÓN DE INFORMACIÓN")
    lines.append("Al terminar el acuerdo, la Parte Receptora devolverá o destruirá toda la Información Confidencial recibida, a opción de la Parte Divulgante.")
    lines.append("")

    if has_jurisdiction:
        juris = "Islas Caimán" if unusual_juris else "Ciudad Autónoma de Buenos Aires"
        lines.append(f"7. JURISDICCIÓN")
        lines.append(f"Este acuerdo se regirá por las leyes de la República Argentina. Las partes se someten a la jurisdicción de los Tribunales Ordinarios de {juris}.")
        lines.append("")

    if has_dataprotection:
        lines.append("8. PROTECCIÓN DE DATOS PERSONALES")
        lines.append("Las partes se comprometen a cumplir con la normativa vigente de protección de datos personales.")
        lines.append("")

    lines.append(f"Firmado en {juris if has_jurisdiction else 'CABA'}, a los {random.randint(1, 28)} días del mes de {random.choice(['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio'])} de 2025.")

    return "\n".join(lines)


def build_invoice_text(template: dict, client_num: int, findings: list[dict]) -> dict:
    """Returns dict with 'text' and programmatic 'total'."""
    t = template
    has_amount_inconsistency = any(f["type"] == "amount_inconsistency" for f in findings)
    has_missing_fields = any(f["type"] == "missing_required_fields" for f in findings)

    invoice_num = f"F-{2025}-{client_num:04d}"
    issue_date = f"{random.randint(1, 28):02d}/{random.randint(1, 12):02d}/2025"
    due_date = f"{random.randint(1, 28):02d}/{random.randint(4, 6):02d}/2025" if not has_missing_fields else ""

    lines = []
    lines.append("FACTURA")
    lines.append("=" * 40)
    lines.append(f"EMISOR: Proveedor Servicios {client_num} S.A.")
    lines.append(f"NIF: 30-{client_num:08d}-{random.randint(0, 9)}")
    lines.append(f"Dirección: Av. Corrientes {random.randint(100, 5000)}, CABA")
    if not has_missing_fields:
        lines.append(f"CLIENTE: Cliente Final {client_num} S.R.L.")
        lines.append(f"NIF CLIENTE: 30-{client_num+100:08d}-{random.randint(0, 9)}")
        lines.append(f"Número de factura: {invoice_num}")
        lines.append(f"Fecha de emisión: {issue_date}")
        if due_date:
            lines.append(f"Fecha de vencimiento: {due_date}")
    else:
        lines.append("(Campos obligatorios incompletos: faltan datos del cliente o número de factura)")
    lines.append("")
    lines.append(f"{'Descripción':<40} {'Cant.':>8} {'P.Unit.':>10} {'Importe':>10}")
    lines.append("-" * 70)

    subtotal = 0
    item_lines = []
    for item_name, qty_spec, price_spec in t["items"]:
        if isinstance(qty_spec, tuple):
            qty = random.randint(*qty_spec)
        else:
            qty = qty_spec
        if isinstance(price_spec, tuple):
            unit_price = round(random.uniform(*price_spec), 2)
        else:
            unit_price = float(price_spec)
        importe = round(qty * unit_price, 2)
        subtotal += importe
        month = random.randint(1, 12)
        desc = item_name.format(month=month)
        item_lines.append(f"{desc:<40} {qty:>8} {unit_price:>10.2f} {importe:>10.2f}")

    vat_rate = t["vat_rate"]
    vat_amount = round(subtotal * vat_rate, 2)

    if has_amount_inconsistency:
        total = round(subtotal + vat_amount + random.choice([100, 500, -200]), 2)
    else:
        total = round(subtotal + vat_amount, 2)

    lines.extend(item_lines)
    lines.append("-" * 70)
    lines.append(f"{'Subtotal:':<58} {subtotal:>10.2f}")
    lines.append(f"{'IVA ({:.0f}%):':<58} {vat_amount:>10.2f}".format(vat_rate * 100))
    lines.append(f"{'TOTAL:':<58} {total:>10.2f}")
    lines.append("")
    lines.append("Forma de pago: Transferencia bancaria")
    lines.append(f"CBU: 00000031{client_num:08d}12345678901")
    lines.append(f"Banco: Banco Nacional {client_num}")

    return {
        "text": "\n".join(lines),
        "subtotal": subtotal,
        "vat": vat_amount,
        "total": total,
        "correct_total": round(subtotal + vat_amount, 2),
        "has_amount_inconsistency": has_amount_inconsistency,
    }


def apply_scan_effects(image: Image.Image) -> Image.Image:
    """Apply noise, rotation, and blur to simulate a scanned document."""
    import numpy as np

    # Rotation (±2 degrees)
    angle = random.uniform(-2, 2)
    image = image.rotate(angle, expand=False, fillcolor=(255, 255, 255), resample=Image.BICUBIC)

    # Gaussian blur (subtle)
    image = image.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.3, 0.8)))

    # Noise
    img_array = np.array(image, dtype=np.float64)
    noise = np.random.normal(0, random.uniform(5, 15), img_array.shape)
    img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(img_array)

    return image


def render_text_to_image(text: str, output_path: Path) -> None:
    """Render plain text to a PNG image using PIL."""
    import textwrap

    lines = text.split("\n")

    # Determine image dimensions
    font_size = 14
    try:
        from PIL import ImageFont
        try:
            font = ImageFont.truetype("Consolas", font_size)
        except OSError:
            font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Estimate dimensions
    char_width = font_size * 0.6
    line_height = font_size * 1.5
    max_chars = 100
    wrapped_lines = []
    for line in lines:
        if len(line) > max_chars:
            wrapped_lines.extend(textwrap.wrap(line, width=max_chars))
        else:
            wrapped_lines.append(line)

    img_width = int(max_chars * char_width * 1.2) + 80
    img_height = int(len(wrapped_lines) * line_height) + 80

    img = Image.new("RGB", (int(img_width), int(img_height)), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    y = 30
    for line in wrapped_lines:
        draw.text((30, y), line, fill=(30, 30, 30), font=font)
        y += line_height

    # Apply scan effects
    img = apply_scan_effects(img)
    img.save(str(output_path))


def text_to_pdf(text: str, output_path: Path) -> None:
    """Render plain text to a PDF using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    rect = page.rect
    # Use a small font and write text
    tw = fitz.TextWriter(rect)
    y_offset = 50
    for line in text.split("\n"):
        if line.strip() == "":
            line = " "
        tw.append(fitz.Point(50, y_offset), line, fontsize=9)
        y_offset += 14
        if y_offset > rect.height - 50:
            tw.write_text(page)
            page = doc.new_page()
            rect = page.rect
            tw = fitz.TextWriter(rect)
            y_offset = 50
    tw.write_text(page)
    doc.save(str(output_path))
    doc.close()


def generate_dataset(preview: bool = False) -> None:
    """Main generation routine."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ground_truth: list[dict[str, Any]] = []

    # Determine which docs are risky
    num_risky = int(NUM_DOCS * (1 - CLEAN_RATIO))
    num_clean = NUM_DOCS - num_risky

    # Assign doc types
    doc_type_list: list[str] = []
    for i in range(NUM_DOCS):
        dtype = random.choices(DOC_TYPES, weights=DOC_TYPES_WEIGHTS)[0]
        doc_type_list.append(dtype)

    # Ensure at least 3 ambiguous cases
    ambiguous_docs = random.sample(range(num_risky), min(3, num_risky))

    risky_count = 0
    clean_count = 0
    total_findings_high = 0
    total_findings = 0
    ambiguous_idx = 0

    doc_count = min(NUM_DOCS, 3) if preview else NUM_DOCS

    for i in range(doc_count):
        doc_id = f"doc-{i+1:04d}"
        doc_type = doc_type_list[i]

        is_risky = risky_count < num_risky and (clean_count >= num_clean or random.random() < 0.6)
        if is_risky:
            risky_count += 1
        else:
            clean_count += 1

        findings: list[dict] = []
        if is_risky:
            possible = FINDINGS_BY_DOCTYPE.get(doc_type, [])
            if possible:
                num_findings = random.choices([1, 2, 3], weights=[0.3, 0.5, 0.2])[0]
                selected = random.sample(possible, min(num_findings, len(possible)))
                findings = [dict(f) for f in selected]

                # Inject ambiguous case
                if ambiguous_idx < len(AMBIGUOUS_SPECS) and ambiguous_idx < len(ambiguous_docs) and ambiguous_idx < risky_count:
                    amb = AMBIGUOUS_SPECS[ambiguous_idx]
                    if amb["doc_type"] == doc_type:
                        amb_finding = next((f for f in FINDINGS_DEFS if f["type"] == amb["finding"]), None)
                        if amb_finding and amb_finding not in findings:
                            findings.append(dict(amb_finding))
                    ambiguous_idx += 1

        # Build document text
        if doc_type == "contract":
            template = random.choice(CONTRACT_TEMPLATES)
            text = build_contract_text(template, i + 1, findings)
            extra_gt = {}
        elif doc_type == "nda":
            template = random.choice(NDA_TEMPLATES)
            text = build_nda_text(template, i + 1, findings)
            extra_gt = {}
        else:  # invoice
            template = random.choice(INVOICE_TEMPLATES)
            result = build_invoice_text(template, i + 1, findings)
            text = result["text"]
            extra_gt = {
                "subtotal": result["subtotal"],
                "vat": result["vat"],
                "total": result["total"],
                "correct_total": result["correct_total"],
                "amount_inconsistency": result["has_amount_inconsistency"],
            }

        # Determine risk level from findings
        if not findings:
            risk_level = "none"
        else:
            severities = [f["severity"] for f in findings]
            if "high" in severities:
                risk_level = "high"
            elif "medium" in severities:
                risk_level = "medium"
            else:
                risk_level = "low"

        # Track severity distribution
        for f in findings:
            total_findings += 1
            if f["severity"] == "high":
                total_findings_high += 1

        # Save .txt
        txt_path = OUTPUT_DIR / f"{doc_id}.txt"
        txt_path.write_text(text, encoding="utf-8")

        # Save .pdf
        pdf_path = OUTPUT_DIR / f"{doc_id}.pdf"
        text_to_pdf(text, pdf_path)

        # Save .png (simulated scan)
        png_path = OUTPUT_DIR / f"{doc_id}.png"
        render_text_to_image(text, png_path)

        # Build findings for ground truth
        gt_findings = []
        for f in findings:
            ftype = f["type"]
            is_amb = ftype in AMBIGUOUS_FINDING_TYPES
            gt_findings.append({
                "type": ftype,
                "severity": f["severity"],
                "description": f["description"],
                "ambiguous": is_amb,
            })

        has_ambiguous = any(fg["ambiguous"] for fg in gt_findings)

        record = {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "risk_level": risk_level,
            "is_risky": is_risky,
            "ambiguous": has_ambiguous,
            "formats": ["txt", "pdf", "png"],
            "findings": gt_findings,
            **extra_gt,
        }
        ground_truth.append(record)

        risk_label = f"RISK={risk_level}" if is_risky else "CLEAN"
        print(f"  [{i+1}/{doc_count}] {doc_id} ({doc_type}) {risk_label} — {len(findings)} findings")

    # Write ground truth
    with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
        for record in ground_truth:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    high_pct = (total_findings_high / total_findings * 100) if total_findings > 0 else 0
    print(f"\n>>> Dataset generated: {OUTPUT_DIR}")
    print(f"    Total documents: {doc_count}")
    print(f"    Clean: {clean_count} | Risky: {risky_count}")
    print(f"    Total findings: {total_findings} (high: {total_findings_high} = {high_pct:.1f}%)")
    print(f"    Ground truth: {GROUND_TRUTH_PATH}")

    if high_pct > 50:
        print(f"    WARNING: High severity > 50% ({high_pct:.1f}%)")


if __name__ == "__main__":
    preview = "--preview" in sys.argv
    generate_dataset(preview=preview)
