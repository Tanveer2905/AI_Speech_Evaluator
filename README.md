# Speech Evaluator (Flask)

**Simple Flask app** that scores a spoken transcript (or pasted text) against a rubric (Excel workbook).  
It provides a web UI, a JSON scoring endpoint, and an Excel report download.

Deployed Application link: https://ai-speech-evaluator.onrender.com/

**Rubric file used by default:**  
`/mnt/data/Case study for interns.xlsx` (place your workbook in the repository root or point `RUBRIC_PATH` env var to it).

---

## Features

- Paste a transcript or upload a `.txt` file.
- Provide duration (seconds) — used to compute WPM (words per minute).
- Computes per-criterion scores using:
  - Rule-based keyword & length checks
  - NLP semantic similarity (optional; sentence-transformers if installed)
  - Data-driven weighting per rubric to combine signals into final scores
- UI shows overall score, word count, sentence count, per-criterion breakdown, and a downloadable Excel `Results` sheet.

---

## Quick start (dev)

> tested with Python 3.10+. Create a virtual environment, install requirements and run the app.

```bash
# from project root
python -m venv .venv
# activate:
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

# Optional: if you plan to use sentence-transformers semantic scoring,
# install the model dependencies (may be large):
# pip install sentence-transformers

# Start the dev server:
python app.py
# App will be available at http://127.0.0.1:5000/
