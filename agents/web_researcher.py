from __future__ import annotations

from typing import List
import re
import io
import requests

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pdfplumber


# =========================
# Utils
# =========================

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


# =========================
# Core extraction
# =========================

def _extract_course_like_lines_from_text(text: str) -> List[str]:
    lines = [_clean_text(x) for x in text.split("\n")]
    lines = [x for x in lines if 6 <= len(x) <= 90]

    bad_contains = (
        "cookies", "privacidad", "aviso legal", "contacto",
        "matricula", "matrícula", "mapa del sitio", "mapa web",
        "copyright", "iniciar sesión", "iniciar sesion",
        "vida universitaria", "servicios universitarios",
        "escuelas y facultades", "estudios de grado",
        "estudios de posgrado", "oferta académica",
        "oferta academica", "futuro estudiante",
        "traslados e intercambios", "empezar en la universidad",
        ":: estudios ::", "datos generales",
    )

    bad_prefixes = (
        "módulo", "modulo", "materia",
        "carácter", "caracter", "ent.", "unid.",
    )

    out: List[str] = []
    for ln in lines:
        lnl = ln.lower()

        if any(b in lnl for b in bad_contains):
            continue

        if any(lnl.startswith(p) for p in bad_prefixes):
            continue

        if not re.search(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]", ln):
            continue

        if re.fullmatch(r"[\d\W]+", ln):
            continue

        if len(ln.split()) < 2:
            continue

        out.append(ln)

    # dedupe
    seen = set()
    uniq = []
    for x in out:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(x)

    return uniq[:300]


def _extract_course_like_lines_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    return _extract_course_like_lines_from_text(soup.get_text("\n"))


# =========================
# Final filter
# =========================

def _final_filter_and_dedupe(courses: List[str]) -> List[str]:
    if not courses:
        return []

    institution_keywords = (
        "escuela", "facultad", "departamento", "universidad",
        "grado en ", "máster", "master", "doctorado",
        "estructuras de investigación", "estructuras de investigacion",
        "i+d", "i+d+i",
    )

    courseish = re.compile(
        r"(fundamentos|introducción|introduccion|ingenier|arquitect|"
        r"sistemas|bases de datos|redes|matem|física|fisica|"
        r"teoría|teoria|comput|seguridad|cloud|machine|"
        r"visión|vision|iot|robótica|robotica|datos|algorit|software)",
        re.I,
    )

    out = []
    seen = set()

    for s in courses:
        l = s.lower()

        if len(s) < 8:
            continue

        if re.search(r"\b(ects|cr[eé]ditos|creditos|semestre|plan|calendario)\b", l):
            continue

        if l.startswith(("módulo", "modulo", "materia")):
            continue

        if any(k in l for k in institution_keywords):
            if not courseish.search(l):
                continue

        if ":" in s and len(s.split()) <= 4:
            continue

        if l not in seen:
            seen.add(l)
            out.append(s)

    return out[:250]


# =========================
# PDF extraction
# =========================

def _extract_text_from_pdf_url(url: str) -> str:
    resp = requests.get(url, allow_redirects=True, timeout=60)
    resp.raise_for_status()

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def extract_courses_from_pdf_urls(urls: List[str]) -> List[str]:
    """
    Descarga PDFs explícitamente y extrae asignaturas.
    Pensado para UPM y casos similares.
    """
    courses: List[str] = []

    for url in urls:
        try:
            text = _extract_text_from_pdf_url(url)
            courses.extend(_extract_course_like_lines_from_text(text))
        except Exception as e:
            print(f"[WARN] PDF failed {url}: {e}")

    return _final_filter_and_dedupe(courses)


# =========================
# HTML scraping (general)
# =========================

def scrape_courses_from_urls(urls: List[str], max_urls: int = 3) -> List[str]:
    courses: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for href in (urls or [])[:max_urls]:
            try:
                page.goto(href, wait_until="domcontentloaded", timeout=30000)
                html = page.content()
                courses.extend(_extract_course_like_lines_from_html(html))
            except Exception:
                # fallback a PDF
                try:
                    text = _extract_text_from_pdf_url(href)
                    courses.extend(_extract_course_like_lines_from_text(text))
                except Exception:
                    print(f"[WARN] {href} skipped (HTML + PDF failed)")

        browser.close()

    return _final_filter_and_dedupe(courses)


def scrape_courses_from_links(links: List[str], max_links: int = 3) -> List[str]:
    return scrape_courses_from_urls(links, max_urls=max_links)


# =========================
# Discover (compat)
# =========================

def discover_program_pages(query: str, max_pages: int = 5) -> List[str]:
    q = query.replace(" ", "+")
    url = f"https://duckduckgo.com/html/?q={q}"

    links: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        soup = BeautifulSoup(page.content(), "lxml")

        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href and href.startswith("http"):
                links.append(href)
            if len(links) >= max_pages:
                break

        browser.close()

    return links
