from __future__ import annotations

from typing import List, Dict, Optional, Tuple, Any
import re
import io
import os
import json
import time
import hashlib
import requests

from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pdfplumber


# =========================
# Utils
# =========================

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or "q"


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:16]


def _cache_dir() -> Path:
    p = Path("artifacts") / "cache_pages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _http_headers() -> dict:
    # headers basicos para reducir bloqueos
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
        "Connection": "keep-alive",
    }


def _is_pdf(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


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
        r"visión|vision|iot|robótica|robotica|datos|algorit|software|"
        r"programación|programacion|informática|informatica)",
        re.I,
    )

    out = []
    seen = set()

    for s in courses:
        l = s.lower()

        if len(s) < 8:
            continue

        # OJO: NO filtramos "plan" en texto final porque a veces sale junto al nombre de asignatura.
        if re.search(r"\b(ects|cr[eé]ditos|creditos|semestre|calendario)\b", l):
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

    return out[:300]


# =========================
# PDF extraction
# =========================

def _extract_text_from_pdf_bytes(b: bytes) -> str:
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _download_bytes(url: str, timeout: int = 45) -> bytes:
    # cache por URL
    cd = _cache_dir()
    key = _sha1(url)
    path = cd / f"{key}.bin"
    if path.exists() and path.stat().st_size > 50:
        return path.read_bytes()

    resp = requests.get(url, headers=_http_headers(), allow_redirects=True, timeout=timeout)
    resp.raise_for_status()
    data = resp.content
    try:
        path.write_bytes(data)
    except Exception:
        pass
    return data


def extract_courses_from_pdf_urls(urls: List[str]) -> List[str]:
    courses: List[str] = []
    for url in urls:
        try:
            b = _download_bytes(url, timeout=60)
            text = _extract_text_from_pdf_bytes(b)
            courses.extend(_extract_course_like_lines_from_text(text))
        except Exception as e:
            print(f"[WARN] PDF failed {url}: {e}")
    return _final_filter_and_dedupe(courses)


# =========================
# HTML scraping (general) + telemetry
# =========================

def scrape_courses_from_urls(
    urls: List[str],
    max_urls: int = 3,
    return_telemetry: bool = False,
) -> List[str] | Tuple[List[str], List[Dict[str, Any]]]:
    """
    Extrae asignaturas de URLs (HTML o PDF) y devuelve lista final.
    Si return_telemetry=True, devuelve (courses, telemetry_per_url).
    """
    courses: List[str] = []
    telemetry: List[Dict[str, Any]] = []

    targets = (urls or [])[:max_urls]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for href in targets:
            item = {
                "url": href,
                "kind": "pdf" if _is_pdf(href) else "html",
                "extracted_lines": 0,
                "error": None,
            }

            try:
                if _is_pdf(href):
                    b = _download_bytes(href, timeout=60)
                    text = _extract_text_from_pdf_bytes(b)
                    lines = _extract_course_like_lines_from_text(text)
                    courses.extend(lines)
                    item["extracted_lines"] = len(lines)
                else:
                    # cache HTML
                    cd = _cache_dir()
                    key = _sha1(href)
                    html_path = cd / f"{key}.html"

                    if html_path.exists() and html_path.stat().st_size > 200:
                        html = html_path.read_text(encoding="utf-8", errors="ignore")
                    else:
                        page.goto(href, wait_until="domcontentloaded", timeout=45000)
                        html = page.content()
                        try:
                            html_path.write_text(html, encoding="utf-8")
                        except Exception:
                            pass

                    lines = _extract_course_like_lines_from_html(html)
                    courses.extend(lines)
                    item["extracted_lines"] = len(lines)

            except Exception as e:
                item["error"] = str(e)

                # fallback: si falla HTML, intentamos como PDF
                if not _is_pdf(href):
                    try:
                        b = _download_bytes(href, timeout=60)
                        text = _extract_text_from_pdf_bytes(b)
                        lines = _extract_course_like_lines_from_text(text)
                        courses.extend(lines)
                        item["kind"] = "pdf_fallback"
                        item["extracted_lines"] = len(lines)
                        item["error"] = None
                    except Exception as e2:
                        item["error"] = f"{item['error']} | PDF fallback failed: {e2}"
                        print(f"[WARN] {href} skipped (HTML + PDF failed)")

            telemetry.append(item)

        browser.close()

    final = _final_filter_and_dedupe(courses)
    if return_telemetry:
        return final, telemetry
    return final


def scrape_courses_from_links(links: List[str], max_links: int = 3) -> List[str]:
    return scrape_courses_from_urls(links, max_urls=max_links, return_telemetry=False)  # compat


# =========================
# Search (Serper) + fallback
# =========================

def _serper_available() -> bool:
    return bool(os.getenv("SERPER_API_KEY", "").strip())


def _serper_search(query: str, num: int = 10) -> Dict:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPER_API_KEY not set")

    gl = os.getenv("SERPER_COUNTRY", "es").strip() or "es"
    hl = os.getenv("SERPER_LANGUAGE", "es").strip() or "es"

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": max(1, min(int(num), 20)),
        "gl": gl,
        "hl": hl,
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _build_query_with_sites(query: str, preferred_domains: Optional[List[str]]) -> str:
    """
    Si preferred_domains existe, agrega filtros site:dominio OR site:dominio2...
    """
    q = (query or "").strip()
    doms = [d.strip() for d in (preferred_domains or []) if (d or "").strip()]
    if not doms:
        return q

    # Serper/Google entiende OR
    sites = " OR ".join([f"site:{d}" for d in doms[:6]])
    return f"{q} ({sites})"


def discover_program_pages(
    query: str,
    max_pages: int = 5,
    preferred_domains: Optional[List[str]] = None,
) -> List[str]:
    """
    Descubre páginas de plan de estudios / asignaturas.
    ✅ Serper.dev (sin captchas)
    ✅ fallback DDG HTML
    Ahora soporta: preferred_domains -> site:domain para resultados oficiales.
    """
    max_pages = max(1, int(max_pages))
    links: List[str] = []

    # =========================
    # 1) Serper (PRO)
    # =========================
    if _serper_available():
        q = _build_query_with_sites(query, preferred_domains)
        try:
            data = _serper_search(q, num=max(10, max_pages * 3))

            for item in (data.get("organic") or []):
                href = item.get("link")
                if href and href.startswith("http"):
                    links.append(href)
                if len(links) >= max_pages:
                    break

            # Debug de serper
            try:
                Path("artifacts").mkdir(parents=True, exist_ok=True)
                dbg = Path("artifacts") / f"serper_debug_{_slugify(q)}.json"
                _write_json(dbg, data)
            except Exception:
                pass

            # dedupe
            seen = set()
            uniq = []
            for x in links:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)

            return uniq[:max_pages]

        except Exception as e:
            print(f"[WARN] Serper search failed → fallback to DDG: {e}")

    # =========================
    # 2) Fallback: DDG HTML (antiguo)
    # =========================
    q = query.replace(" ", "+")
    url = f"https://duckduckgo.com/html/?q={q}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        html = page.content()

        # debug ddg
        try:
            Path("artifacts").mkdir(parents=True, exist_ok=True)
            Path("artifacts/ddg_debug.html").write_text(html, encoding="utf-8")
        except Exception:
            pass

        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href and href.startswith("http"):
                links.append(href)
            if len(links) >= max_pages:
                break

        browser.close()

    # dedupe
    seen = set()
    uniq = []
    for x in links:
        if x not in seen:
            seen.add(x)
            uniq.append(x)

    return uniq[:max_pages]
