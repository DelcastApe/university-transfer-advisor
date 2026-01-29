from __future__ import annotations

from pathlib import Path
import pandas as pd
import yaml

from core.llm import groq_chat


def _load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def generate_recommendation(
    comparison_csv: str,
    mission_yaml: str,
) -> str:
    """
    Genera una recomendación EJECUTIVA y concisa usando Groq.
    Pensada para leerse en 1–2 minutos.
    """

    df = pd.read_csv(comparison_csv).sort_values("final_score", ascending=False)
    cfg = _load_yaml(mission_yaml)

    my_profile = cfg.get("my_profile", {}) or {}
    pref = (my_profile.get("preferences", {}) or {})
    current = cfg.get("current_studies", {}) or {}

    student_name = my_profile.get("name", "Jhonnatan")

    weight_match = float(pref.get("weight_match", 0.55))
    weight_prestige = float(pref.get("weight_prestige", 0.25))
    weight_cost = float(pref.get("weight_cost", 0.20))

    destination_degree = current.get(
        "degree", "Grado en Ingenieria Informatica"
    )

    # Top universidades
    best = df.iloc[0]
    second = df.iloc[1] if len(df) > 1 else None
    third = df.iloc[2] if len(df) > 2 else None

    prompt = f"""
Eres un asesor académico experto en traslados universitarios en España.

CONTEXTO
- Estudiante: {student_name}
- Carrera destino: {destination_degree}
- Decisión basada en convalidación, prestigio y costo de vida.

PESOS DEL SISTEMA
- Convalidación: {weight_match * 100:.0f}%
- Prestigio: {weight_prestige * 100:.0f}%
- Costo de vida: {weight_cost * 100:.0f}%

RESULTADOS (ORDENADOS POR SCORE FINAL)
1) {best.university} ({best.city})
   - Convalidación: {best.match_pct}%
   - Prestigio: {best.prestige_score}
   - Costo de vida (score): {best.cost_score}
   - Score final: {best.final_score}

2) {second.university if second is not None else "-"}
3) {third.university if third is not None else "-"}

INSTRUCCIONES
- Dirígete directamente a {student_name}.
- Recomienda UNA universidad (la #1).
- Explica en 2–3 párrafos el POR QUÉ (trade-off principal).
- Menciona brevemente por qué las otras quedan detrás.
- Incluye una sección: PLAN DE ACCION (3 a 5 pasos, muy concretos).
- Usa español claro y profesional.
- NO escribas un informe largo.
- NO repitas tablas ni números innecesarios.
- NO uses Markdown, solo texto con saltos de línea.
"""

    return groq_chat(
        prompt=prompt,
        system=(
            "Eres un asesor académico universitario. "
            "Respondes de forma clara, directa y concisa."
        ),
        temperature=0.25,
    )
