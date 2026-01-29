from __future__ import annotations

from typing import Dict
from pathlib import Path
import json
import re
import requests

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from core.models import CostComponent, LivingCostBreakdown


# =========================
# Cache
# =========================

def _cache_dir() -> Path:
    p = Path("artifacts") / "cost_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _slugify_city(city: str) -> str:
    s = (city or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "city"


def _http_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
        "Connection": "keep-alive",
    }


# =========================
# Scraping helpers
# =========================

def _parse_numbeo_html(html: str) -> Dict[str, float]:
    prices: Dict[str, float] = {}
    soup = BeautifulSoup(html, "lxml")

    for row in soup.select("table.data_wide_table tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) != 2:
            continue

        label, value = cols
        value = value.replace("€", "").replace(",", "").strip()

        try:
            price = float(value)
        except ValueError:
            continue

        label_l = label.lower()

        if "apartment (1 bedroom) outside of centre" in label_l:
            prices["rent"] = price
        elif "meal, inexpensive restaurant" in label_l:
            prices["meal"] = price
        elif "monthly pass" in label_l:
            prices["transport"] = price
        elif "internet" in label_l:
            prices["internet"] = price
        elif "utilities" in label_l and "basic" in label_l:
            prices["utilities"] = price
        elif "fitness club" in label_l:
            prices["gym"] = price

    return prices


def _scrape_numbeo_requests(city: str) -> Dict[str, float]:
    url_city = city.replace(" ", "-")
    url = f"https://www.numbeo.com/cost-of-living/in/{url_city}"

    resp = requests.get(url, headers=_http_headers(), timeout=30)
    resp.raise_for_status()
    return _parse_numbeo_html(resp.text)


def _scrape_numbeo_playwright(city: str) -> Dict[str, float]:
    url_city = city.replace(" ", "-")
    url = f"https://www.numbeo.com/cost-of-living/in/{url_city}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        html = page.content()
        browser.close()

    return _parse_numbeo_html(html)


def _fallback_city_mid(city: str) -> Dict[str, float]:
    """
    Fallbacks razonables para no tumbar el batch.
    Claves: rent, meal, transport, utilities, internet, gym
    """
    c = (city or "").lower()
    if "madrid" in c:
        return {"rent": 1200, "meal": 14, "transport": 55, "utilities": 120, "internet": 40, "gym": 35}
    if "barcelona" in c:
        return {"rent": 1150, "meal": 14, "transport": 45, "utilities": 120, "internet": 40, "gym": 35}
    if "valencia" in c:
        return {"rent": 900, "meal": 12, "transport": 40, "utilities": 110, "internet": 38, "gym": 30}
    if "sevilla" in c:
        return {"rent": 800, "meal": 12, "transport": 35, "utilities": 105, "internet": 38, "gym": 30}
    if "granada" in c:
        return {"rent": 650, "meal": 11, "transport": 35, "utilities": 100, "internet": 35, "gym": 28}
    if "zaragoza" in c:
        return {"rent": 700, "meal": 12, "transport": 35, "utilities": 105, "internet": 35, "gym": 28}
    # default
    return {"rent": 750, "meal": 12, "transport": 35, "utilities": 105, "internet": 35, "gym": 28}


# =========================
# Main API
# =========================

def estimate_living_cost_city(city: str) -> LivingCostBreakdown:
    """
    Devuelve un LivingCostBreakdown con gastos descompuestos.
    PRO:
      - cache por ciudad
      - requests-first (rapido)
      - fallback a playwright
      - fallback por ciudad si Numbeo bloquea
    """
    url_city = city.replace(" ", "-")
    source = f"https://www.numbeo.com/cost-of-living/in/{url_city}"

    cache_path = _cache_dir() / f"numbeo_{_slugify_city(city)}.json"

    # cache hit
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            data = cached.get("prices") or {}
            confidence = cached.get("confidence") or "MEDIUM"
        except Exception:
            data, confidence = {}, "MEDIUM"
    else:
        data = {}
        confidence = "MEDIUM"

        # 1) requests
        try:
            data = _scrape_numbeo_requests(city)
            confidence = "HIGH" if data else "MEDIUM"
        except Exception:
            # 2) playwright fallback
            try:
                data = _scrape_numbeo_playwright(city)
                confidence = "MEDIUM" if data else "LOW"
            except Exception:
                # 3) hard fallback
                data = _fallback_city_mid(city)
                confidence = "LOW"

        try:
            cache_path.write_text(
                json.dumps(
                    {"city": city, "source": source, "prices": data, "confidence": confidence},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # =========================
    # Descomposición (habitación compartida)
    # =========================
    housing_mid = float(data.get("rent", 750.0)) * 0.6
    food_mid = float(data.get("meal", 12.0)) * 30
    transport_mid = float(data.get("transport", 35.0))
    utilities_mid = float(data.get("utilities", 105.0)) * 0.5 + float(data.get("internet", 35.0))
    leisure_mid = float(data.get("gym", 28.0)) + 40.0

    def component(mid: float) -> CostComponent:
        return CostComponent(
            min=round(mid * 0.85, 2),
            max=round(mid * 1.15, 2),
            sources=[source],
        )

    housing = component(housing_mid)
    food = component(food_mid)
    transport = component(transport_mid)
    utilities = component(utilities_mid)
    leisure = component(leisure_mid)

    total_min = round(housing.min + food.min + transport.min + utilities.min + leisure.min, 2)
    total_max = round(housing.max + food.max + transport.max + utilities.max + leisure.max, 2)

    return LivingCostBreakdown(
        housing=housing,
        food=food,
        transport=transport,
        utilities=utilities,
        leisure=leisure,
        total_min=total_min,
        total_max=total_max,
        confidence=confidence,
    )


def cost_score(monthly_min: float, monthly_max: float) -> float:
    mid = (monthly_min + monthly_max) / 2.0
    score = 100.0 * (1500.0 - mid) / (1500.0 - 700.0)
    score = max(0.0, min(100.0, score))
    return round(score, 2)
