from __future__ import annotations


def prestige_score(university_name: str) -> float:
    """
    MVP: score 0-100 por prestigio.
    Luego lo reemplazamos por:
      - scraping de rankings (QS/THE/ARWU) + fuentes
      - indicadores de empleabilidad
    """
    name = (university_name or "").lower()

    # Valores razonables para demo (no definitivos)
    if "politecnica de madrid" in name or "upm" in name:
        return 90.0
    if "politecnica de catalunya" in name or "upc" in name:
        return 88.0
    if "politecnica de valencia" in name or "upv" in name:
        return 85.0

    return 75.0
