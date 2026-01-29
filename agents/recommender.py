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
    Recomendación personalizada (ES) usando Groq, basada en:
    - missions/transfer.yaml (pesos, my_profile, current_studies)
    - missions/my_curriculum.yaml (origen real)
    - artifacts/comparison.csv (resultados objetivos)
    """

    df = pd.read_csv(comparison_csv)
    cfg = _load_yaml(mission_yaml)

    # ✅ de transfer.yaml
    my_profile = cfg.get("my_profile", {}) or {}
    pref = (my_profile.get("preferences", {}) or {})
    current = cfg.get("current_studies", {}) or {}

    student_name = my_profile.get("name", "Jhonnatan")
    residence_country = my_profile.get("country", "Spain")
    currency = my_profile.get("currency", "EUR")

    weight_match = float(pref.get("weight_match", 0.55))
    weight_prestige = float(pref.get("weight_prestige", 0.25))
    weight_cost = float(pref.get("weight_cost", 0.20))

    destination_degree = current.get("degree", "Grado en Ingenieria Informatica")

    # ✅ origen desde curriculum_file
    curriculum_file = current.get("curriculum_file", "missions/my_curriculum.yaml")
    cur = _load_yaml(curriculum_file)

    origin_country = cur.get("origin_country", "Peru")
    origin_degree = cur.get("origin_degree", "Ingenieria en Computacion y Sistemas")
    origin_uni = cur.get("university_origin", "Universidad de origen")

    # Tabla para prompt (objetiva)
    table_md = df.to_markdown(index=False)

    # Detectar universidades con datos pobres (ej. UPM bloqueada)
    # Si match_pct == 0 y extracted no existe aquí, igual se puede advertir.
    possible_data_issues = []
    for _, row in df.iterrows():
        try:
            if float(row.get("match_pct", 0)) == 0.0:
                possible_data_issues.append(str(row.get("university")))
        except Exception:
            pass

    data_issue_note = ""
    if possible_data_issues:
        data_issue_note = (
            "\nNOTA DE CALIDAD DE DATOS:\n"
            f"- En estas universidades el match curricular puede estar subestimado (posible extracción fallida): "
            + ", ".join(possible_data_issues)
            + "\n- Si hay 0% de convalidación pero la universidad es prestigiosa, revisa la fuente (PDF/plan) manualmente.\n"
        )

    prompt = f"""
Eres un asesor académico universitario experto en traslados y convalidaciones en España.
Tu respuesta debe ser MUY personalizada para el estudiante y sonar profesional (estilo informe).

ESTUDIANTE
- Nombre: {student_name}
- País de origen: {origin_country}
- Universidad de origen: {origin_uni}
- Carrera de origen: {origin_degree}
- Carrera destino equivalente en España: {destination_degree}
- País de residencia actual: {residence_country}
- Moneda: {currency}

CRITERIOS DE DECISIÓN (PESOS DEL SISTEMA)
- Convalidación curricular: {weight_match * 100:.0f}%
- Prestigio académico: {weight_prestige * 100:.0f}%
- Costo de vida: {weight_cost * 100:.0f}%

RESULTADOS OBJETIVOS DEL SISTEMA (NO MODIFICAR NÚMEROS)
{table_md}
{data_issue_note}

INSTRUCCIONES
- Dirígete directamente a {student_name}.
- Usa un tono claro, cercano y profesional (como asesor real).
- Analiza cada universidad: ventajas, desventajas y riesgos.
- Incluye una sección: "Qué significa este resultado para mi convalidacion".
- Recomienda UNA universidad como la opción más conveniente según los pesos.
- Justifica comparando explícitamente con las otras 2.
- Cierra con un plan de acción de 5 pasos (qué hacer la próxima semana).
- Escribe en ESPAÑOL.
- Evita Markdown (no uses #, **, *). Usa títulos con MAYÚSCULAS y saltos de línea.
"""

    return groq_chat(
        prompt=prompt,
        system="Eres un asesor académico universitario. Respondes en español y en formato de informe.",
        temperature=0.25,
    )
