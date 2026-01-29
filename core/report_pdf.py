from pathlib import Path
from typing import List
import re

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
    """
    Convierte Markdown basico del LLM a HTML simple compatible con ReportLab.
    """
    if not text:
        return ""

    # Titulos -> bold
    text = re.sub(r"^### (.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^## (.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^# (.+)$", r"<b>\1</b>", text, flags=re.M)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Bullets
    text = re.sub(r"^\* (.+)$", r"• \1", text, flags=re.M)

    # Quitar restos de #
    text = text.replace("#", "")

    return text


def _bar_chart(df: pd.DataFrame) -> Drawing:
    drawing = Drawing(460, 240)

    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 40
    chart.height = 160
    chart.width = 360

    chart.data = [df["final_score"].tolist()]
    chart.categoryAxis.categoryNames = df["university"].tolist()

    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 10

    chart.bars[0].fillColor = colors.HexColor("#4F46E5")

    drawing.add(chart)
    return drawing


# =========================
# Main PDF generator
# =========================

def generate_pdf_report(
    text: str,
    output_path: str | Path,
    comparison_csv: str = "artifacts/comparison.csv",
):
    output_path = str(Path(output_path))

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="TitleBig",
            fontSize=22,
            spaceAfter=20,
            alignment=1,
        )
    )

    styles.add(
        ParagraphStyle(
            name="Section",
            fontSize=15,
            spaceBefore=16,
            spaceAfter=10,
            textColor=colors.HexColor("#1F2937"),
        )
    )

    story: List = []

    # =========================
    # Portada
    # =========================
    story.append(Paragraph("Informe de Recomendación Universitaria", styles["TitleBig"]))
    story.append(
        Paragraph(
            "Análisis personalizado para traslado y convalidación académica",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 40))
    story.append(PageBreak())

    # =========================
    # Tabla comparativa
    # =========================
    df = pd.read_csv(comparison_csv)

    story.append(Paragraph("Comparación de Universidades", styles["Section"]))

    def cell(v):
        return Paragraph(str(v), styles["Normal"])

    table_data = [[cell(c) for c in df.columns]]
    for row in df.values.tolist():
        table_data.append([cell(v) for v in row])

    table = Table(
        table_data,
        colWidths=[140, 80, 60, 60, 60, 70, 120],
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (2, 1), (-2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 24))

    # =========================
    # Grafico
    # =========================
    story.append(Paragraph("Comparación de Puntuación Final", styles["Section"]))
    story.append(_bar_chart(df))
    story.append(PageBreak())

    # =========================
    # Texto del LLM
    # =========================
    story.append(Paragraph("Análisis y Recomendación Personalizada", styles["Section"]))

    clean_text = _clean_llm_markdown(text)

    for block in clean_text.split("\n\n"):
        # ⚠️ SOLO escapamos &, no < ni >
        safe_block = block.replace("&", "&amp;").replace("\n", "<br/>")

        story.append(
            Paragraph(
                safe_block,
                styles["Normal"],
            )
        )
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
