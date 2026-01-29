from __future__ import annotations

from typing import Tuple, List
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def estimate_living_cost_city(city: str) -> Tuple[float, float, List[str]]:
    """
    MVP: devuelve un rango mensual estimado (EUR) y algunas fuentes encontradas.
    Luego lo refinamos con scraping real de 2-3 fuentes confiables.
    """
    q = f"cost of living {city} per month student"
    url = f"https://duckduckgo.com/html/?q={q.replace(' ', '+')}"

    sources: List[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        html = page.content()
        soup = BeautifulSoup(html, "lxml")

        for a in soup.select("a.result__a")[:3]:
            href = a.get("href")
            if href and href.startswith("http"):
                sources.append(href)

        browser.close()

    c = city.lower()

    # Rangos MVP (aprox estudiantes, piso compartido)
    if "madrid" in c:
        return 1100.0, 1450.0, sources
    if "barcelona" in c:
        return 1050.0, 1400.0, sources
    if "valencia" in c:
        return 850.0, 1150.0, sources
    if "leon" in c or "león" in c:
        return 700.0, 950.0, sources

    return 750.0, 1050.0, sources


def cost_score(monthly_min: float, monthly_max: float) -> float:
    """
    Convierte coste a score 0-100 (mas barato => mas score).
    Normalizacion simple para MVP.
    """
    mid = (monthly_min + monthly_max) / 2.0

    # 700 -> 100, 1500 -> 0
    score = 100.0 * (1500.0 - mid) / (1500.0 - 700.0)
    if score < 0:
        score = 0.0
    if score > 100:
        score = 100.0
    return round(score, 2)
