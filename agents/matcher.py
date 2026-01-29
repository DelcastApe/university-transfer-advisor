from __future__ import annotations

from rapidfuzz import fuzz
from typing import List, Tuple, Dict, Any
import json

from core.llm import groq_available, groq_chat


def _llm_equivalence(course_a: str, course_b: str) -> tuple[bool, float, str]:
    """
    Decide si dos asignaturas son equivalentes (para convalidacion) y devuelve:
      (equivalent: bool, confidence_0_1: float, reason: str)

    Solo se usa para casos dudosos.
    """
    system = (
        "Eres un asesor academico experto en convalidacion de asignaturas entre Peru y Espana "
        "para Ingenieria Informatica. Responde SOLO en JSON valido."
    )

    prompt = f"""
Decide si estas dos asignaturas probablemente son equivalentes para convalidacion.
Considera que los nombres pueden variar entre universidades.

Asignatura A: "{course_a}"
Asignatura B: "{course_b}"

Devuelve JSON con este esquema exacto:
{{
  "equivalent": true/false,
  "confidence": 0.0-1.0,
  "reason": "frase corta"
}}

Reglas:
- Si es claramente distinta, equivalent=false.
- Si suena muy cercana (mismo tema core), equivalent=true.
- confidence alto (>=0.8) solo si es muy claro.
"""

    out = groq_chat(prompt, system=system, temperature=0.1)

    try:
        data = json.loads(out)
        eq = bool(data.get("equivalent", False))
        conf = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", "")).strip()
        conf = max(0.0, min(1.0, conf))
        if not reason:
            reason = "LLM: no reason provided"
        return eq, conf, reason
    except Exception:
        # fallback seguro
        return False, 0.0, f"LLM parse error: {out[:120]}"


def match_percentage_with_notes(
    my_courses: List[str],
    uni_courses: List[str],
    fuzzy_threshold: int = 75,
    llm_band: tuple[int, int] = (55, 74),
    llm_conf_threshold: float = 0.70,
) -> tuple[float, List[Dict[str, Any]]]:
    """
    Retorna:
      - porcentaje de cursos con match
      - notas (mapeos) para reporte

    Notas: lista de dicts:
      {
        "my_course": ...,
        "best_match": ...,
        "method": "fuzzy"|"llm"|"none",
        "score": int,
        "llm_conf": float,
        "reason": str
      }
    """
    if not my_courses:
        return 0.0, []
    if not uni_courses:
        return 0.0, [{"my_course": c, "best_match": None, "method": "none", "score": 0, "llm_conf": 0.0, "reason": "No uni courses"} for c in my_courses]

    hits = 0
    notes: List[Dict[str, Any]] = []

    for mc in my_courses:
        best_score = -1
        best_uc = None

        for uc in uni_courses:
            score = fuzz.token_set_ratio(mc.lower(), uc.lower())
            if score > best_score:
                best_score = score
                best_uc = uc

        # Caso 1: match claro por fuzz
        if best_score >= fuzzy_threshold:
            hits += 1
            notes.append({
                "my_course": mc,
                "best_match": best_uc,
                "method": "fuzzy",
                "score": int(best_score),
                "llm_conf": 0.0,
                "reason": "High fuzzy similarity"
            })
            continue

        # Caso 2: banda dudosa -> LLM decide
        low, high = llm_band
        if low <= best_score <= high and groq_available() and best_uc:
            eq, conf, reason = _llm_equivalence(mc, best_uc)
            if eq and conf >= llm_conf_threshold:
                hits += 1
                notes.append({
                    "my_course": mc,
                    "best_match": best_uc,
                    "method": "llm",
                    "score": int(best_score),
                    "llm_conf": float(conf),
                    "reason": reason
                })
            else:
                notes.append({
                    "my_course": mc,
                    "best_match": best_uc,
                    "method": "none",
                    "score": int(best_score),
                    "llm_conf": float(conf),
                    "reason": f"LLM says not equivalent (conf={conf:.2f}) - {reason}"
                })
            continue

        # Caso 3: sin match
        notes.append({
            "my_course": mc,
            "best_match": best_uc,
            "method": "none",
            "score": int(best_score),
            "llm_conf": 0.0,
            "reason": "Below threshold"
        })

    pct = round(100.0 * hits / max(1, len(my_courses)), 2)
    return pct, notes
