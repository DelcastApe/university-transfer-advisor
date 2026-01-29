from __future__ import annotations

from typing import Dict, List


def prestige_score(university_name: str) -> Dict:
    """
    Heurística de prestigio académico (0–100) respaldada por fuentes públicas.

    DEVUELVE:
    {
        "score": float,
        "sources": [url, ...],
        "confidence": "LOW|MEDIUM|HIGH"
    }
    """
    name = (university_name or "").lower()

    sources: List[str] = []
    score = 70.0
    confidence = "LOW"

    # =========================
    # Politécnicas españolas
    # =========================
    if "politecnica de madrid" in name or "upm" in name:
        score = 92.0
        confidence = "HIGH"
        sources = [
            "https://en.wikipedia.org/wiki/Universidad_Polit%C3%A9cnica_de_Madrid",
            "https://www.topuniversities.com/universities/universidad-politecnica-de-madrid",
        ]

    elif "politecnica de catalunya" in name or "upc" in name:
        score = 89.0
        confidence = "HIGH"
        sources = [
            "https://en.wikipedia.org/wiki/Polytechnic_University_of_Catalonia",
            "https://www.topuniversities.com/universities/polytechnic-university-catalonia",
        ]

    elif "politecnica de valencia" in name or "upv" in name:
        score = 86.0
        confidence = "MEDIUM"
        sources = [
            "https://en.wikipedia.org/wiki/Universitat_Polit%C3%A8cnica_de_Val%C3%A8ncia",
            "https://www.topuniversities.com/universities/universitat-politecnica-de-valencia",
        ]

    # =========================
    # Universidades generales
    # =========================
    elif "universidad de león" in name:
        score = 72.0
        confidence = "MEDIUM"
        sources = [
            "https://en.wikipedia.org/wiki/University_of_Le%C3%B3n",
        ]

    return {
        "score": score,
        "sources": sources,
        "confidence": confidence,
    }
