from __future__ import annotations

from pathlib import Path
from typing import List
import re
import json

import pandas as pd
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart


# =========================
# Utils
# =========================

def _clean_llm_markdown(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"^\* (.+)$", r"• \1", text, flags=re.M)
    return text


def _slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or "uni"


def _load_json_artifact(prefix: str, uni: str) -> dict | None:
    path = Path("artifacts") / f"{prefix}_{_slugify(uni)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe(s: str) -> str:
    # evita que reportlab rompa por caracteres especiales tipo &
    return (s or "").replace("&", "&amp;")


# =========================
# Blocks
# =========================

def _cost_block(title: str, comp: dict, styles) -> List:
    lines = [
        f"• Vivienda: {comp['housing']['min']} – {comp['housing']['max']} EUR",
        f"• Alimentación: {comp['food']['min']} – {comp['food']['max']} EUR",
        f"• Transporte: {comp['transport']['min']} – {comp['transport']['max']} EUR",
        f"• Servicios: {comp['utilities']['min']} – {comp['utilities']['max']} EUR",
        f"• Ocio básico: {comp['leisure']['min']} – {comp['leisure']['max']} EUR",
        "",
        f"<b>Total estimado:</b> {comp['total_min']} – {comp['total_max']} EUR / mes",
        f"Confianza: {comp.get('confidence','MEDIUM')}",
    ]

    out: List = [Paragraph(f"<b>{_safe(title)}</b>", styles["Normal"])]
    for l in lines:
        out.append(Paragraph(_safe(str(l)), styles["Normal"]))
    out.append(Spacer(1, 12))
    return out


def _prestige_block(title: str, pres: dict, styles) -> List:
    score = pres.get("score", None)
    conf = pres.get("confidence", "LOW")
    sources = pres.get("sources") or []

    out: List = [Paragraph(f"<b>{_safe(title)}</b>", styles["Normal"])]

    if score is None:
        out.append(Paragraph("• Score: N/A", styles["Normal"]))
    else:
        out.append(Paragraph(f"• Score: {float(score):.1f} / 100", styles["Normal"]))

    out.append(Paragraph(f"• Confianza: { _safe(str(conf)) }", styles["Normal"]))

    if sources:
        out.append(Paragraph("• Fuentes:", styles["Normal"]))
        for s in sources[:6]:
            # No hacemos hyperlink (reportlab necesita tags <a> y a veces falla),
            # lo dejamos como texto para que sea robusto.
            out.append(Paragraph(f"  - {_safe(str(s))}", styles["Normal"]))
    else:
        out.append(Paragraph("• Fuentes: (no disponibles)", styles["Normal"]))

    out.append(Spacer(1, 12))
    return out


def _telemetry_block(title: str, telemetry_doc: dict, styles, max_rows: int = 6) -> List:
    """
    Lee artifacts/sources_<uni>.json si existe y muestra resumen.
    """
    telem = (telemetry_doc or {}).get("telemetry") or []
    if not telem:
        return []

    out: List = [Paragraph(f"<b>{_safe(title)}</b>", styles["Normal"])]
    out.append(Paragraph("Resumen de extracción (telemetría):", styles["Normal"]))

    shown = 0
    for t in telem:
        if shown >= max_rows:
            break
        url = t.get("url", "")
        kind = t.get("kind", "")
        lines = t.get("extracted_lines", 0)
        err = t.get("error", None)

        if err:
            out.append(Paragraph(f"• {kind} | lines={lines} | ERROR | {_safe(url)}", styles["Normal"]))
        else:
            out.append(Paragraph(f"• {kind} | lines={lines} | OK | {_safe(url)}", styles["Normal"]))
        shown += 1

    if len(telem) > shown:
        out.append(Paragraph(f"• ... ({len(telem) - shown} mas)", styles["Normal"]))

    out.append(Spacer(1, 12))
    return out


# =========================
# Charts & tables
# =========================

def _bar_chart(df: pd.DataFrame, title_mode: str = "short") -> Drawing:
    drawing = Drawing(460, 240)

    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 40
    chart.height = 160
    chart.width = 360

    chart.data = [df["final_score"].tolist()]

    if title_mode == "full":
        names = df["university"].tolist()
    else:
        names = [
            str(u).replace("Universitat", "Univ.").replace("Universidad", "Univ.")
            for u in df["university"].tolist()
        ]

    chart.categoryAxis.categoryNames = names
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 10

    chart.bars[0].fillColor = colors.HexColor("#4F46E5")

    drawing.add(chart)
    return drawing


def _build_table(df: pd.DataFrame, styles, limit: int | None = None) -> Table:
    headers = ["Universidad", "Ciudad", "Match %", "Prestigio", "Costo", "Score final", "Notas"]
    table_data = [[Paragraph(h, styles["TableCell"]) for h in headers]]

    use_df = df.copy()
    if limit is not None:
        use_df = use_df.head(limit)

    for _, r in use_df.iterrows():
        table_data.append(
            [
                Paragraph(_safe(str(r["university"]).replace(" ", "<br/>", 2)), styles["TableCell"]),
                Paragraph(_safe(str(r["city"])), styles["TableCell"]),
                Paragraph(f'{float(r["match_pct"]):.1f}%', styles["TableCell"]),
                Paragraph(f'{float(r["prestige_score"]):.0f}', styles["TableCell"]),
                Paragraph(f'{float(r["cost_score"]):.1f}', styles["TableCell"]),
                Paragraph(f'{float(r["final_score"]):.2f}', styles["TableCell"]),
                Paragraph(_safe(str(r.get("notes", ""))).replace("|", "<br/>"), styles["TableCell"]),
            ]
        )

    table = Table(table_data, colWidths=[150, 55, 50, 55, 55, 60, 120], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (2, 1), (5, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


# =========================
# Main PDF generator
# =========================

def generate_pdf_report(
    llm_text: str,
    output_path: str | Path,
    comparison_csv: str = "artifacts/comparison.csv",
):
    output_path = str(Path(output_path))
    df = pd.read_csv(comparison_csv)

    # ordenar por score final
    if "final_score" in df.columns:
        df = df.sort_values("final_score", ascending=False).reset_index(drop=True)

    top6 = df.head(6).copy()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("TitleBig", fontSize=22, spaceAfter=14, alignment=1))
    styles.add(ParagraphStyle("Subtitle", fontSize=12, spaceAfter=24, alignment=1, textColor=colors.grey))
    styles.add(ParagraphStyle("Section", fontSize=15, spaceBefore=18, spaceAfter=10))
    styles.add(ParagraphStyle("TableCell", fontSize=9, leading=11))

    story: List = []

    # =========================
    # Portada
    # =========================
    story.append(Paragraph("Recomendación Universitaria", styles["TitleBig"]))
    story.append(Paragraph("Comparación objetiva y recomendación generada por IA", styles["Subtitle"]))
    story.append(PageBreak())

    # =========================
    # TOP 6
    # =========================
    story.append(Paragraph("TOP 6 Universidades Recomendadas", styles["Section"]))
    story.append(
        Paragraph(
            "Este TOP 6 está ordenado por Score final (0–100) según tus pesos: convalidación, prestigio y costo de vida.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 10))

    story.append(_build_table(top6, styles))
    story.append(Spacer(1, 18))

    story.append(Paragraph("Gráfico: Score final (TOP 6)", styles["Section"]))
    story.append(_bar_chart(top6, title_mode="short"))
    story.append(PageBreak())

    # =========================
    # Tabla completa
    # =========================
    story.append(Paragraph("Comparación Completa (todas las universidades)", styles["Section"]))
    story.append(_build_table(df, styles))
    story.append(Spacer(1, 18))

    # =========================
    # Gráfico completo
    # =========================
    story.append(Paragraph("Puntuación Final Comparada (todas)", styles["Section"]))
    story.append(_bar_chart(df, title_mode="short"))
    story.append(PageBreak())

    # =========================
    # Coste de vida por ciudad
    # =========================
    story.append(Paragraph("Gastos mensuales estimados por ciudad", styles["Section"]))
    story.append(
        Paragraph(
            "Valores estimados por categorías (vivienda, alimentación, etc.). Se calculan desde fuentes públicas (ej. Numbeo) y fallbacks razonables.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 10))

    for _, r in df.iterrows():
        uni = str(r["university"])
        city = str(r["city"])
        cost = _load_json_artifact("living_cost", uni)
        if cost:
            story.extend(_cost_block(f"{uni} ({city})", cost, styles))

    story.append(PageBreak())

    # =========================
    # Prestigio + fuentes
    # =========================
    story.append(Paragraph("Prestigio académico y fuentes (transparencia)", styles["Section"]))
    story.append(
        Paragraph(
            "Cada score de prestigio incluye fuentes y una confianza aproximada. Esto sirve para auditar el resultado.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 10))

    for _, r in df.iterrows():
        uni = str(r["university"])
        city = str(r["city"])
        pres = _load_json_artifact("prestige", uni)
        if pres:
            story.extend(_prestige_block(f"{uni} ({city})", pres, styles))
        else:
            story.extend(_prestige_block(f"{uni} ({city})", {"score": None, "sources": [], "confidence": "LOW"}, styles))

    story.append(PageBreak())

    # =========================
    # (Opcional) Telemetría scraping
    # =========================
    story.append(Paragraph("Evidencia de scraping (telemetría)", styles["Section"]))
    story.append(
        Paragraph(
            "Resumen de URLs usadas y cuántas líneas se extrajeron. Si una universidad sale con pocos datos, aquí lo ves.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 10))

    for _, r in df.iterrows():
        uni = str(r["university"])
        tel = _load_json_artifact("sources", uni)
        block = _telemetry_block(uni, tel, styles, max_rows=6)
        if block:
            story.extend(block)

    story.append(PageBreak())

    # =========================
    # Recomendación LLM
    # =========================
    story.append(Paragraph("Recomendación Personalizada", styles["Section"]))
    for block in _clean_llm_markdown(llm_text).split("\n\n"):
        story.append(Paragraph(_safe(block).replace("\n", "<br/>"), styles["Normal"]))
        story.append(Spacer(1, 12))

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    doc.build(story)
