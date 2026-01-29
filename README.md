# 🎓 University Transfer Agent (Spain)

**University Transfer Agent** is a Python-based system designed to help international students **decide which Spanish university to transfer to in order to graduate**, using an objective, explainable, and automated analysis.

The project compares universities based on:

- ✅ Course validation / curriculum similarity  
- 🎓 Academic prestige  
- 💰 Cost of living in the city  
- 🤖 AI-generated personalized recommendation  
- 📄 Professional PDF report

It is built for **real-world university transfer scenarios**, using official study plans, intelligent matching, and automated reporting.

---

## 🚀 Main Use Case

An international student (e.g. from Peru) who wants to:

- Maximize **course validation**
- Maintain strong **academic prestige**
- Control **living costs**
- Receive a **clear, personalized recommendation** to support decision-making

---

## 🧠 How It Works

### 1️⃣ Student Profile Ingestion
- Country of origin
- Current degree
- Completed courses (loaded from YAML)
- Decision preferences (weights)

### 2️⃣ Study Plan Extraction
- Scraping from **official university URLs**
- Supports:
  - HTML pages
  - PDF documents
- Aggressive filtering of institutional noise

### 3️⃣ Course Matching
- **RapidFuzz** for string similarity
- **LLM (Groq)** for ambiguous cases
- One-to-one course matching evidence per university

### 4️⃣ Scoring
- Curriculum match percentage
- Academic prestige score (MVP)
- Cost of living score
- Final weighted score

### 5️⃣ AI Recommendation
- LLM analyzes all results
- Generates a **personalized academic recommendation**
- Written directly to the student

### 6️⃣ PDF Report Generation
- Full comparison table
- Visual charts
- Per-university analysis
- Final recommendation

---

## 🗂️ Project Structure

```text
university-transfer-agent/
│
├── agents/
│   ├── web_researcher.py     # HTML + PDF scraping
│   ├── matcher.py            # Fuzzy + LLM matching
│   ├── living_cost.py        # City living cost estimation
│   └── recommender.py        # LLM-based recommendation
│
├── core/
│   ├── models.py             # Pydantic models
│   ├── llm.py                # Groq API wrapper
│   ├── scoring.py            # Prestige scoring
│   └── report_pdf.py         # PDF report generation
│
├── missions/
│   ├── transfer.yaml         # Main mission config
│   └── my_curriculum.yaml    # Student curriculum
│
├── artifacts/
│   ├── comparison.csv
│   ├── matches_<university>.json
│   └── transfer_recommendation.pdf
│
├── run.py                    # Main orchestrator
├── README.md
└── .env
````

---

## ⚙️ Requirements

* Python **3.10+**
* Playwright
* pdfplumber
* pandas
* pydantic v2
* reportlab
* Groq SDK (optional but recommended)

Install dependencies:

```bash
pip install -r requirements.txt
playwright install
```

---

## 🔐 Environment Variables

Create a `.env` file:

```env
GROQ_API_KEY=your_api_key
GROQ_MODEL=llama-3.1-8b-instant
```

> The LLM is used **only when it adds value** (ambiguous matching and final recommendation).

---

## ▶️ Run the Project

```bash
python run.py
```

Generated outputs:

* `artifacts/comparison.csv`
* `artifacts/matches_<university>.json`
* `artifacts/transfer_recommendation.pdf`

---

## 📄 Output Example (PDF)

The final report includes:

* Professional cover page
* Complete comparison table
* Score visualization chart
* Per-university analysis
* Personalized recommendation

---

## 🧪 Project Status

✅ End-to-end pipeline working
✅ Real scraping from official study plans
✅ Hybrid fuzzy + LLM matching
✅ Professional PDF report
✅ Real academic transfer use case

---

## 🔮 Future Improvements

* Integration with real rankings (QS / THE)
* Cached institutional PDFs
* Credit-weighted matching (ECTS)
* Web UI (FastAPI / Streamlit)
* DOCX export
* Multi-language support

---

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

```

