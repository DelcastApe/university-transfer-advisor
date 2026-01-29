# University Transfer Agent (Spain) — Autonomous Ranking + PDF Report

An autonomous Python-based agent to help you choose the best university in Spain to transfer and graduate from, optimizing:
- Course validation (curriculum match)
- Academic prestige (with evidence and sources)
- Cost of living by city (with category breakdown)

The system produces a ranking (CSV) and a professional PDF report with a TOP 6, full comparison table, charts, cost breakdowns, and an AI-generated personalized recommendation.


## What the system does (pipeline)

For each target university:

### 1) Autonomous discovery (internet)
- Automatically searches for relevant “study plan / courses” pages using Serper.dev.
- Applies “official-ish” filters and URL scoring (penalizes noise like news, blogs, rankings, events).
- Saves discovery evidence:
  - `artifacts/discovery_<uni>.json` (queries, candidates, selected URLs, scoring reasons)

### 2) Course extraction (HTML / PDF)
- Extracts “course-like” lines from:
  - HTML pages (Playwright)
  - PDF documents (pdfplumber)
- Caches downloaded pages/files in `artifacts/cache_pages/` to reduce blocking and speed up runs.
- Saves per-URL telemetry:
  - `artifacts/sources_<uni>.json` (URL, html/pdf, extracted lines count, errors)

### 3) Curriculum matching
- Compares your courses (from `missions/my_curriculum.yaml`) with extracted university courses.
- Computes `match_pct` and detailed matching notes.
- Saves evidence:
  - `artifacts/matches_<uni>.json`

### 4) Cost of living by city (breakdown)
- Estimates monthly expenses by category:
  - Housing, Food, Transport, Utilities, Leisure
- Converts cost into a normalized `cost_score` (cheaper = higher score).
- Saves:
  - `artifacts/living_cost_<uni>.json`

### 5) Prestige with sources (updated)
- `prestige_score()` now returns an auditable object:
  ```json
  {
    "score": 0-100,
    "sources": ["..."],
    "confidence": "LOW | MEDIUM | HIGH"
  }

* The runner stores:

  * `artifacts/prestige_<uni>.json`
* The final score uses the prestige score without breaking the pipeline.

### 6) Final scoring

Final score (0–100) is computed as:

* `match_pct * weight_match`
* `prestige_score * weight_prestige`
* `cost_score * weight_cost`

### 7) PDF report + AI recommendation

* Saves ranking:

  * `artifacts/comparison.csv`
* Generates a professional PDF including:

  * TOP 6 universities
  * Full comparison table
  * Bar charts
  * Monthly cost breakdowns per city
  * AI-generated personalized recommendation
* Output:

  * `artifacts/transfer_recommendation.pdf`

## Requirements

* Python 3.11+ (3.12 recommended)
* Chromium (for Playwright)

Installation:

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

Quick install (if no `requirements.txt` yet):

```bash
pip install requests playwright beautifulsoup4 lxml pdfplumber pandas pydantic pyyaml reportlab python-dotenv groq
playwright install chromium
```

## Environment variables (.env)

Create a `.env` file at the project root:

```env
# Search (recommended)
SERPER_API_KEY=YOUR_SERPER_API_KEY
SERPER_COUNTRY=es
SERPER_LANGUAGE=es

# LLM (narrative recommendation)
GROQ_API_KEY=YOUR_GROQ_API_KEY
GROQ_MODEL=llama-3.1-70b-versatile
```

Notes:

* Serper.dev provides stable Google-like search without captchas.
* Never commit `.env` files to GitHub.

## Mission configuration

Edit `missions/transfer.yaml`:

* Set your weights:

  * `weight_match`, `weight_prestige`, `weight_cost`
* Point to your curriculum file:

  * `current_studies.curriculum_file: missions/my_curriculum.yaml`
* Define target universities.

Example (excerpt):

```yaml
id: transfer-v1
goal: "Find the best university..."
my_profile:
  name: "Jhonnatan Del Castillo"
  country: "Spain"
  currency: "EUR"
  preferences:
    weight_match: 0.55
    weight_prestige: 0.25
    weight_cost: 0.20

current_studies:
  degree: "Bachelor in Computer Engineering"
  curriculum_file: "missions/my_curriculum.yaml"

targets:
  universities:
    - name: "Universidad Politecnica de Madrid"
      city: "Madrid"
      program_query: "grado ingenieria informatica plan de estudios asignaturas"
```

Your curriculum goes in `missions/my_curriculum.yaml` as a list of courses.

## Running the agent

Standard run:

```bash
python run.py --mission missions/transfer.yaml
```

Run only N universities (debugging):

```bash
python run.py --mission missions/transfer.yaml --limit 6
```

Force full refresh:

```bash
python run.py --mission missions/transfer.yaml --refresh
```

Refresh individual stages:

```bash
python run.py --mission missions/transfer.yaml --refresh-discovery
python run.py --mission missions/transfer.yaml --refresh-matching
python run.py --mission missions/transfer.yaml --refresh-cost
```

## Generated artifacts (`artifacts/`)

Global:

* `comparison.csv` — final ranking
* `transfer_recommendation.pdf` — final report (TOP 6, tables, charts, costs, AI recommendation)

Per university:

* `discovery_<uni>.json` — discovery queries, candidates, selected URLs, scoring reasons
* `sources_<uni>.json` — telemetry (URLs used, html/pdf, extracted lines, errors)
* `matches_<uni>.json` — curriculum match percentage and notes
* `living_cost_<uni>.json` — monthly cost breakdown with sources
* `prestige_<uni>.json` — prestige score, confidence, and sources

Cache:

* `cache_pages/` — cached HTML and PDF files (reduces blocking and speeds up runs)

## Transparency & auditability

This project is designed to be auditable:

* You can trace exactly which URLs were used for each university.
* You can inspect how many course lines were extracted per source.
* Curriculum matching is fully inspectable.
* Prestige scores include explicit sources and confidence levels.
* Cost of living is broken down by category with stored evidence.

## Legal & good practices

* Intended for educational and personal research use.
* Respects websites’ ToS and robots.txt.
* No paywall bypassing or authentication circumvention.
* Scraping is limited (few URLs per university + caching).
* Never commit API keys or private data to the repository.

## Roadmap (next steps)

* Fully automated prestige discovery from QS / THE / ARWU with stored evidence.
* Improved cost-of-living fallbacks when data is missing.
* More robust PDF extraction (scanned PDFs, complex layouts).
* Smarter URL ranking to avoid non-curricular documents.
* Optional UI/dashboard to explore evidence without opening JSON files.

## 👤 Author

**Jhonnatan Del Castillo**
Academic / technical project focused on real-world university mobility problems.

---

## ⭐ Final Note

This project is suitable as:

* 💼 A strong portfolio project
* 🎓 A real academic decision support tool
* 🤖 An advanced applied LLM use case

If you find it useful, consider giving it a ⭐


