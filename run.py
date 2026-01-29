from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
import pandas as pd

from core.models import Mission, ResultRow
from agents.web_researcher import (
    discover_program_pages,
    scrape_courses_from_links,
    scrape_courses_from_urls,
    extract_courses_from_pdf_urls,
)
from agents.matcher import match_percentage_with_notes
from agents.living_cost import estimate_living_cost_city, cost_score
from core.scoring import prestige_score

from agents.recommender import generate_recommendation
from core.report_pdf import generate_pdf_report


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_mission(path: str) -> Mission:
    return Mission(**load_yaml(path))


def load_my_courses(mission: Mission) -> list[str]:
    """
    Si current_studies.curriculum_file existe, lo usa.
    Si no, usa current_studies.courses inline.
    """
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


def main():
    print("▶ Loading mission...")
    mission = load_mission("missions/transfer.yaml")

    my_courses = load_my_courses(mission)
    print(f"▶ My courses loaded: {len(my_courses)}")

    results = []

    # ✅ targets ahora es un objeto Targets, no dict
    for u in mission.targets.universities:
        uni = u.name
        city = u.city
        query = u.program_query or ""
        program_urls = u.program_urls or []

        print(f"\n▶ Processing: {uni}")

        # (si algún día agregas UPM, aquí puedes volver a usar el caso especial)
        if "madrid" in uni.lower():
            print("  - UPM detected → using direct PDF extraction")
            links = program_urls
            uni_courses = extract_courses_from_pdf_urls(program_urls)
        else:
            if program_urls:
                links = program_urls
                uni_courses = scrape_courses_from_urls(program_urls, max_urls=3)
            else:
                links = discover_program_pages(f"{uni} {query}", max_pages=5)
                uni_courses = scrape_courses_from_links(links, max_links=3)

        print(f"  - Extracted {len(uni_courses)} possible course lines")

        match_pct, notes = match_percentage_with_notes(my_courses, uni_courses)

        # Guardar evidencia por universidad
        out_json = Path("artifacts") / f"matches_{slugify(uni)}.json"
        out_json.parent.mkdir(parents=True, exist_ok=True)

        out_json.write_text(
            json.dumps(
                {
                    "university": uni,
                    "city": city,
                    "query": query,
                    "links": links,
                    "program_urls": program_urls,
                    "my_courses_count": len(my_courses),
                    "uni_courses_count": len(uni_courses),
                    "match_pct": match_pct,
                    "matches": notes,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  - Saved: {out_json}")

        pres = prestige_score(uni)
        mn, mx, _ = estimate_living_cost_city(city)
        cscore = cost_score(mn, mx)

        pref = mission.my_profile.preferences
        final_score = (
            pref.weight_match * match_pct
            + pref.weight_prestige * pres
            + pref.weight_cost * cscore
        )

        results.append(
            ResultRow(
                university=uni,
                city=city,
                match_pct=match_pct,
                prestige_score=pres,
                cost_score=cscore,
                final_score=round(final_score, 2),
                notes=f"cost~{mn}-{mx} EUR/mo | links={len(links)} | extracted={len(uni_courses)}",
            ).model_dump()
        )

    # =========================
    # Summary artifacts
    # =========================
    Path("artifacts").mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results).sort_values("final_score", ascending=False)
    df.to_csv("artifacts/comparison.csv", index=False)

    print("\n▶ Generating recommendation PDF...")
    recommendation = generate_recommendation(
        comparison_csv="artifacts/comparison.csv",
        mission_yaml="missions/transfer.yaml",
    )

    generate_pdf_report(
        text=recommendation,
        output_path="artifacts/transfer_recommendation.pdf",
        comparison_csv="artifacts/comparison.csv",
    )

    print("✔ Done. PDF generated: artifacts/transfer_recommendation.pdf")


if __name__ == "__main__":
    main()
