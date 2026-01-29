from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml
import pandas as pd

from core.models import Mission, ResultRow
from agents.web_researcher import (
    discover_program_pages,
    scrape_courses_from_urls,   # 👈 usamos telemetry
    scrape_courses_from_links,
    extract_courses_from_pdf_urls,
)
from agents.matcher import match_percentage_with_notes
from agents.living_cost import estimate_living_cost_city, cost_score
from core.scoring import prestige_score  # 👈 ahora devuelve dict {score,sources,confidence}
from agents.recommender import generate_recommendation
from core.report_pdf import generate_pdf_report


# =========================
# IO helpers
# =========================

def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_mission(path: str) -> Mission:
    return Mission(**load_yaml(path))


def load_my_courses(mission: Mission) -> list[str]:
    cs = mission.current_studies

    if cs.curriculum_file:
        cur = load_yaml(cs.curriculum_file)
        courses = cur.get("courses", []) or []
        names: list[str] = []
        for c in courses:
            n = str(c.get("name", "")).strip()
            if n:
                names.append(n)
        return names

    if cs.courses:
        return [c.name for c in cs.courses]

    return []


def slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or "uni"


def _read_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# =========================
# URL helpers
# =========================

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _is_pdf(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def _dedupe_keep_order(urls: list[str]) -> list[str]:
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _filter_officialish(urls: list[str]) -> list[str]:
    out = []
    for url in urls:
        d = _domain(url)
        if not d:
            continue
        if any(x in d for x in ("facebook.", "twitter.", "tiktok.", "instagram.", "linkedin.", "youtube.")):
            continue

        # dominios tipicos universitarios
        if d.endswith(".es") or d.endswith(".edu") or d.endswith(".edu.es"):
            out.append(url)
        else:
            # permitimos PDF aunque el dominio no sea "perfecto"
            if _is_pdf(url):
                out.append(url)

    return _dedupe_keep_order(out)


def _matches_preferred_domain(d: str, preferred_domains: list[str]) -> bool:
    if not d:
        return False
    for pd in preferred_domains or []:
        pd = (pd or "").lower().strip()
        if not pd:
            continue
        if d == pd or d.endswith("." + pd) or pd.endswith("." + d):
            return True
    return False


def _score_url(url: str, query: str, preferred_domains: list[str]) -> tuple[int, list[str]]:
    u = url.lower()
    d = _domain(url)
    reasons: list[str] = []
    score = 0

    # dominio preferido (oficial)
    if _matches_preferred_domain(d, preferred_domains):
        score += 70
        reasons.append(f"+70 dominio preferido ({d})")

    # señales de plan/guia/asignaturas
    strong = [
        ("plan-de-estudios", 40),
        ("plan_estudios", 40),
        ("plan de estudios", 30),
        ("asignaturas", 40),
        ("guia-docente", 40),
        ("guia_docente", 40),
        ("guía docente", 30),
        ("ects", 20),
        ("plan", 15),
    ]
    for kw, pts in strong:
        if kw in u:
            score += pts
            reasons.append(f"+{pts} contiene '{kw}'")

    if _is_pdf(url):
        score += 25
        reasons.append("+25 es PDF")

    # penalizaciones
    bad = [("noticia", 20), ("news", 20), ("evento", 15), ("blog", 20), ("ranking", 20)]
    for kw, pts in bad:
        if kw in u:
            score -= pts
            reasons.append(f"-{pts} contiene '{kw}' (ruido)")

    # bonus leve si la query apunta a informatica y la url tiene informatica/computer
    q = (query or "").lower()
    if "informatica" in q and ("informatica" in u or "computer" in u or "informatics" in u):
        score += 10
        reasons.append("+10 relacionado con informatica")

    return score, reasons


def _discover_and_rank(
    uni: str,
    query: str,
    preferred_domains: list[str],
    max_pages: int = 12,
    top_k: int = 4,
) -> dict:
    q1 = f"{uni} {query}"
    q2 = f"{uni} {query} pdf"

    # ✅ ahora pasamos preferred_domains -> Serper usa site:
    raw1 = discover_program_pages(q1, max_pages=max_pages, preferred_domains=preferred_domains)
    raw2 = discover_program_pages(q2, max_pages=max_pages, preferred_domains=preferred_domains)

    raw = _dedupe_keep_order((raw1 or []) + (raw2 or []))
    filtered = _filter_officialish(raw)

    candidates = []
    for url in filtered:
        score, reasons = _score_url(url, query=query, preferred_domains=preferred_domains or [])
        candidates.append(
            {"url": url, "domain": _domain(url), "score": score, "reasons": reasons, "is_pdf": _is_pdf(url)}
        )

    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = [c["url"] for c in candidates[: max(1, top_k)]]

    return {
        "queries": [q1, q2],
        "preferred_domains": preferred_domains or [],
        "selected": selected,
        "candidates": candidates,
    }


# =========================
# Main
# =========================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mission", default="missions/transfer.yaml", help="Ruta del YAML de mision")
    ap.add_argument("--limit", type=int, default=0, help="Correr solo N universidades (0 = todas)")
    ap.add_argument("--refresh", action="store_true", help="Recalcular TODO (discovery, matching, living cost y prestigio)")
    ap.add_argument("--refresh-discovery", action="store_true", help="Recalcular solo discovery")
    ap.add_argument("--refresh-matching", action="store_true", help="Recalcular solo matching (scrape + match)")
    ap.add_argument("--refresh-cost", action="store_true", help="Recalcular solo living cost")
    ap.add_argument("--refresh-prestige", action="store_true", help="Recalcular solo prestigio")  # 👈 NUEVO
    args = ap.parse_args()

    refresh_discovery = args.refresh or args.refresh_discovery
    refresh_matching = args.refresh or args.refresh_matching
    refresh_cost = args.refresh or args.refresh_cost
    refresh_prestige = args.refresh or args.refresh_prestige

    print("▶ Loading mission...")
    mission = load_mission(args.mission)

    my_courses = load_my_courses(mission)
    print(f"▶ My courses loaded: {len(my_courses)}")

    Path("artifacts").mkdir(parents=True, exist_ok=True)

    universities = mission.targets.universities
    if args.limit and args.limit > 0:
        universities = universities[: args.limit]

    results: list[dict] = []

    for u in universities:
        uni = u.name
        city = u.city
        query = u.program_query or ""
        preferred_domains = getattr(u, "preferred_domains", None) or []

        print(f"\n▶ Processing: {uni}")

        disc_path = Path("artifacts") / f"discovery_{slugify(uni)}.json"
        match_path = Path("artifacts") / f"matches_{slugify(uni)}.json"
        cost_path = Path("artifacts") / f"living_cost_{slugify(uni)}.json"
        sources_path = Path("artifacts") / f"sources_{slugify(uni)}.json"
        prestige_path = Path("artifacts") / f"prestige_{slugify(uni)}.json"  # 👈 NUEVO

        # =========================
        # 1) Discovery (cacheable)
        # =========================
        discovery = None
        if (not refresh_discovery) and disc_path.exists():
            discovery = _read_json(disc_path)
            if discovery:
                print(f"  - Loaded cached discovery: {disc_path.name}")

        if discovery is None:
            try:
                ranked = _discover_and_rank(
                    uni=uni,
                    query=query,
                    preferred_domains=preferred_domains,
                    max_pages=12,
                    top_k=5 if "madrid" in (city or "").lower() or "madrid" in uni.lower() else 4,
                )
                discovery = {
                    "university": uni,
                    "city": city,
                    "program_query": query,
                    "queries_used": ranked["queries"],
                    "preferred_domains": ranked["preferred_domains"],
                    "selected": ranked["selected"],
                    "candidates": ranked["candidates"],
                }
                _write_json(disc_path, discovery)
                print(f"  - Saved: {disc_path}")
            except Exception as e:
                print(f"  [WARN] Discovery failed for {uni}: {e}")
                discovery = {
                    "university": uni,
                    "city": city,
                    "program_query": query,
                    "queries_used": [],
                    "preferred_domains": preferred_domains,
                    "selected": [],
                    "candidates": [],
                }
                _write_json(disc_path, discovery)
                print(f"  - Saved (empty): {disc_path}")

        links = (discovery.get("selected") or [])[:5]

        # =========================
        # 2) Matching (cacheable) + TELEMETRIA
        # =========================
        match_pct = 0.0
        notes = []
        uni_courses_count = 0

        cached_match = None
        if (not refresh_matching) and match_path.exists():
            cached_match = _read_json(match_path)
            if cached_match and "match_pct" in cached_match and "matches" in cached_match:
                match_pct = float(cached_match.get("match_pct") or 0.0)
                notes = cached_match.get("matches") or []
                uni_courses_count = int(cached_match.get("uni_courses_count") or 0)
                print(f"  - Loaded cached matching: {match_path.name}")

        if cached_match is None:
            try:
                pdf_links = [x for x in links if _is_pdf(x)]
                html_links = [x for x in links if not _is_pdf(x)]

                telemetry = []

                # UPM PDF-first
                if "madrid" in uni.lower() or "politecnica de madrid" in uni.lower() or "upm" in uni.lower():
                    if pdf_links:
                        print("  - UPM: PDFs detected → extracting from PDFs")
                        uni_courses = extract_courses_from_pdf_urls(pdf_links[:3])

                        telemetry = [
                            {"url": x, "kind": "pdf", "extracted_lines": None, "note": "pdf extractor (no telemetry)"}
                            for x in pdf_links[:3]
                        ]

                        if len(uni_courses) < 40 and html_links:
                            print("  - UPM: low PDF extraction → trying HTML as fallback")
                            extra, t = scrape_courses_from_urls(html_links[:2], max_urls=2, return_telemetry=True)
                            uni_courses = uni_courses + extra
                            telemetry.extend(t)
                    else:
                        uni_courses, telemetry = scrape_courses_from_urls(html_links[:3], max_urls=3, return_telemetry=True)

                else:
                    uni_courses, telemetry = scrape_courses_from_urls(links[:3], max_urls=3, return_telemetry=True)

                uni_courses = list(dict.fromkeys(uni_courses))
                uni_courses_count = len(uni_courses)
                print(f"  - Extracted {uni_courses_count} possible course lines")

                # guardar sources telemetry
                _write_json(
                    sources_path,
                    {
                        "university": uni,
                        "city": city,
                        "links_used": links[:3],
                        "telemetry": telemetry,
                    },
                )
                print(f"  - Saved: {sources_path}")

                match_pct, notes = match_percentage_with_notes(my_courses, uni_courses)

                _write_json(
                    match_path,
                    {
                        "university": uni,
                        "city": city,
                        "query": query,
                        "links": links,
                        "preferred_domains": preferred_domains,
                        "my_courses_count": len(my_courses),
                        "uni_courses_count": uni_courses_count,
                        "match_pct": match_pct,
                        "matches": notes,
                    },
                )
                print(f"  - Saved: {match_path}")

            except Exception as e:
                print(f"  [WARN] Matching failed for {uni}: {e}")
                _write_json(
                    match_path,
                    {
                        "university": uni,
                        "city": city,
                        "query": query,
                        "links": links,
                        "preferred_domains": preferred_domains,
                        "my_courses_count": len(my_courses),
                        "uni_courses_count": 0,
                        "match_pct": 0.0,
                        "matches": [],
                        "error": str(e),
                    },
                )
                print(f"  - Saved (failed): {match_path}")
                match_pct, notes, uni_courses_count = 0.0, [], 0

        # =========================
        # 3) Living cost (cacheable)
        # =========================
        living_cost = None
        if (not refresh_cost) and cost_path.exists():
            try:
                living_cost = _read_json(cost_path)
                if living_cost:
                    print(f"  - Loaded cached living cost: {cost_path.name}")
            except Exception:
                living_cost = None

        if living_cost is None:
            try:
                lc = estimate_living_cost_city(city)
                living_cost = json.loads(lc.model_dump_json(indent=2, ensure_ascii=False))
                cost_path.write_text(json.dumps(living_cost, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  - Saved: {cost_path}")
            except Exception as e:
                print(f"  [WARN] Living cost failed for {uni}/{city}: {e}")
                living_cost = None

        if living_cost:
            cscore = cost_score(float(living_cost["total_min"]), float(living_cost["total_max"]))
            cost_note = f"{living_cost['total_min']}-{living_cost['total_max']} EUR/mes"
        else:
            cscore = 50.0
            cost_note = "unknown"

        # =========================
        # 4) Prestigio (cacheable) + fuentes
        # =========================
        pres_obj = None
        if (not refresh_prestige) and prestige_path.exists():
            pres_obj = _read_json(prestige_path)
            if pres_obj:
                print(f"  - Loaded cached prestige: {prestige_path.name}")

        if pres_obj is None:
            try:
                pres_obj = prestige_score(uni)  # devuelve dict
                if not isinstance(pres_obj, dict):
                    pres_obj = {"score": float(pres_obj), "sources": [], "confidence": "LOW"}
                _write_json(prestige_path, pres_obj)
                print(f"  - Saved: {prestige_path}")
            except Exception as e:
                print(f"  [WARN] Prestige failed for {uni}: {e}")
                pres_obj = {"score": 70.0, "sources": [], "confidence": "LOW"}
                try:
                    _write_json(prestige_path, pres_obj)
                except Exception:
                    pass

        try:
            pres = float((pres_obj or {}).get("score", 70.0))
        except Exception:
            pres = 70.0

        prest_conf = (pres_obj or {}).get("confidence", "LOW")

        # =========================
        # 5) Final scoring
        # =========================
        pref = mission.my_profile.preferences
        final_score = (
            pref.weight_match * float(match_pct)
            + pref.weight_prestige * float(pres)
            + pref.weight_cost * float(cscore)
        )

        results.append(
            ResultRow(
                university=uni,
                city=city,
                match_pct=float(match_pct),
                prestige_score=float(pres),
                cost_score=float(cscore),
                final_score=round(float(final_score), 2),
                living_cost=None,  # PDF lee desde artifacts/living_cost_*.json
                notes=(
                    f"autonomo | links={len(links)} | extracted={uni_courses_count} | "
                    f"cost={cost_note} | prestige={pres:.0f}({prest_conf})"
                ),
            ).model_dump()
        )

    # =========================
    # CSV + PDF
    # =========================
    df = pd.DataFrame(results).sort_values("final_score", ascending=False)
    df.to_csv("artifacts/comparison.csv", index=False)

    print("\n▶ Generating recommendation PDF...")
    recommendation = generate_recommendation(
        comparison_csv="artifacts/comparison.csv",
        mission_yaml=args.mission,
    )

    generate_pdf_report(
        llm_text=recommendation,
        output_path="artifacts/transfer_recommendation.pdf",
        comparison_csv="artifacts/comparison.csv",
    )

    print("✔ Done. PDF generated: artifacts/transfer_recommendation.pdf")
    print("✔ Ranking saved: artifacts/comparison.csv")


if __name__ == "__main__":
    main()
