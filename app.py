import io
import os
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd

from scoring import compute_scores_for_transcript
from rubric_loader import load_rubric

app = Flask(__name__, static_folder="static", template_folder="templates")

# Use the workbook path you uploaded in your environment.
RUBRIC_PATH = "/mnt/data/Case study for interns.xlsx"

# Try to load rubric on startup (optional)
try:
    rubric_df = load_rubric(RUBRIC_PATH)
except Exception as e:
    rubric_df = None
    app.logger.warning(f"[WARN] Could not load rubric: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/score", methods=["POST"])
def score():
    """
    Accepts:
      - pasted transcript via form field "transcript"
      - uploaded .txt via form file "file"
      - optional duration in seconds via form field "duration_seconds"
    Returns JSON with overall_score, word_count, sentence_count, duration_seconds_used and per_criterion.
    """
    uploaded_file = request.files.get("file")
    text = request.form.get("transcript", "").strip()
    duration_raw = request.form.get("duration_seconds", "").strip()

    if uploaded_file and uploaded_file.filename:
        try:
            text = uploaded_file.read().decode("utf-8").strip()
        except Exception:
            uploaded_file.seek(0)
            text = uploaded_file.read().decode("latin-1").strip()

    if not text:
        return jsonify({"error": "No transcript provided (paste text or upload a .txt file)."}), 400

    try:
        duration_seconds = float(duration_raw) if duration_raw else None
    except Exception:
        duration_seconds = None

    out_json, _ = compute_scores_for_transcript(text, duration_seconds=duration_seconds)
    return jsonify(out_json)

@app.route("/score_excel", methods=["POST"])
def score_excel():
    """
    Same inputs but returns an Excel file with a Results sheet and original rubric sheets (if readable).
    """
    uploaded_file = request.files.get("file")
    text = request.form.get("transcript", "").strip()
    duration_raw = request.form.get("duration_seconds", "").strip()

    if uploaded_file and uploaded_file.filename:
        try:
            text = uploaded_file.read().decode("utf-8").strip()
        except Exception:
            uploaded_file.seek(0)
            text = uploaded_file.read().decode("latin-1").strip()

    if not text:
        return jsonify({"error": "No transcript provided (paste text or upload a .txt file)."}), 400

    try:
        duration_seconds = float(duration_raw) if duration_raw else None
    except Exception:
        duration_seconds = None

    out_json, df_out = compute_scores_for_transcript(text, duration_seconds=duration_seconds)

    # Create Excel in-memory and send
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Write original rubric sheets if available
        try:
            if os.path.exists(RUBRIC_PATH):
                original = pd.read_excel(RUBRIC_PATH, sheet_name=None, engine="openpyxl")
                for sheet_name, sheet_df in original.items():
                    safe_name = sheet_name[:31] if sheet_name else "Sheet"
                    sheet_df.to_excel(writer, sheet_name=safe_name, index=False)
        except Exception:
            pass

        # Write results sheet (df_out already contains sentence count and duration rows)
        df_out.to_excel(writer, sheet_name="Results", index=False)

    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name="scoring_results.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    # for local testing only
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
