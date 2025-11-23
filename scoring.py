import re
import math
import pandas as pd

# Optional libraries (we attempt to import; if missing we fall back to heuristics)
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except Exception:
    _vader = None

try:
    import language_tool_python
    _lt_tool = language_tool_python.LanguageTool('en-US')
except Exception:
    _lt_tool = None

# Optional semantic model used only for extra feedback (not required)
_sem_model = None
_sem_util = None
def _load_semantic_model():
    global _sem_model, _sem_util
    if _sem_model is None:
        try:
            from sentence_transformers import SentenceTransformer, util
            _sem_model = SentenceTransformer("all-MiniLM-L6-v2")
            _sem_util = util
        except Exception:
            _sem_model = None
            _sem_util = None
    return _sem_model, _sem_util

# Filler words list for clarity metric
_FILLER_WORDS = set([
    "um","uh","like","you know","so","actually","basically","right","i mean",
    "well","kind of","sort of","okay","hmm","erm","ah","uhm","ahh"
])

# Content & Structure must-have keywords (from your rubric)
_CONTENT_KEYWORDS_MUST = [
    "name","age","school","class","family","hobbies","interests",
    "ambition","goal","dream","fun fact","strength","achievement"
]
# map synonyms to canonical tokens (simple)
_KEYWORD_SYNONYMS = {
    "school/class":"school",
    "class/school":"school",
    "hobbies/interests":"hobbies",
    "what they do in free time":"hobbies",
    "ambition/goal/dream":"ambition",
    "strengths or achievements":"strength"
}

def _normalize_keywords(raw_list):
    out = []
    for s in raw_list:
        s = str(s).strip().lower()
        if not s:
            continue
        # substitute synonyms
        for k,v in _KEYWORD_SYNONYMS.items():
            if k in s:
                s = s.replace(k, v)
        out.append(s)
    return out

_CONTENT_KEYWORDS_MUST = _normalize_keywords(_CONTENT_KEYWORDS_MUST)

# util: tokenize words
def _word_tokens(text):
    return re.findall(r"\b\w+\b", str(text).lower())

def _word_count(text):
    return len(_word_tokens(text))

def _unique_word_count(text):
    toks = _word_tokens(text)
    return len(set(toks))

def _ttr(text):
    toks = _word_tokens(text)
    if not toks:
        return 0.0
    return len(set(toks)) / len(toks)

def _detect_keywords(text, keywords):
    """
    Return list of keywords found from keywords (token exact or substring)
    """
    txt_lower = text.lower()
    tokens = set(_word_tokens(text))
    found = []
    for kw in keywords:
        kw_l = kw.lower()
        # exact token or substring
        if kw_l in tokens:
            found.append(kw)
        elif kw_l in txt_lower:
            found.append(kw)
    return found

def _compute_salutation_score(text):
    """
    Salutation bands:
      - No salutation: 0
      - Normal (Hi, Hello): 2
      - Good (Good Morning, Good Afternoon...): 4
      - Excellent: includes "I am excited to introduce" or "I am excited to introduce myself": 5
    Max = 5 (rubric)
    """
    txt = text.lower()
    if "i am excited to introduce" in txt or "i'm excited to introduce" in txt:
        return 5, "Excellent salutation phrase found."
    # check good greetings
    for g in ["good morning", "good afternoon", "good evening", "good day"]:
        if g in txt:
            return 4, f"Found greeting '{g}'."
    # normal
    for g in ["hi ", "hello ", "hi,", "hello,"]:
        if g in txt:
            return 2, f"Found greeting '{g.strip()}'."
    return 0, "No salutation detected."

def _compute_flow_score(text):
    """
    Flow: order followed (Salutation -> Basic details (name, age, class/school) -> Additional -> Closing)
    If order roughly matches, award 5, else 0.
    We'll approximate by trying to locate keyword positions and checking order.
    """
    txt = text.lower()
    tokens = _word_tokens(txt)
    positions = {}
    # keywords to check for order positions
    order_keys = {
        "salutation": ["hi","hello","good morning","good afternoon","good evening","good day","i am excited"],
        "name": ["name","i am","i'm","my name is"],
        "age": ["age","i am \d","i'm \d","years old"],
        "school": ["school","class","college"],
        "additional": ["hobbies","interest","hobby","fun fact","strength","achievement","ambition","goal","dream"],
        "closing": ["thank you","thanks for listening","thank you for listening","thankyou"]
    }
    # find first occurrence index for each marker
    idx_map = {}
    for k, kws in order_keys.items():
        idx_map[k] = None
        for kw in kws:
            m = re.search(re.escape(kw), txt)
            if m:
                idx = m.start()
                if idx_map[k] is None or idx < idx_map[k]:
                    idx_map[k] = idx
    # consider flow good if salutation < name/age < additional < closing (where present)
    order_sequence = ["salutation","name","age","school","additional","closing"]
    prev_idx = -1
    satisfied = True
    for key in order_sequence:
        idx = idx_map.get(key)
        if idx is not None:
            if idx < prev_idx:
                satisfied = False
                break
            prev_idx = idx
    return (5 if satisfied else 0), ("Flow followed" if satisfied else "Flow not followed / out of order")

def _compute_wpm(word_count, duration_seconds):
    if duration_seconds and duration_seconds > 0:
        minutes = duration_seconds / 60.0
        return word_count / minutes
    # fallback: assume duration 60s if not provided -> WPM = words per minute if text delivered in ~60s
    return word_count

def _score_speech_rate(wpm):
    """
    Bands:
    >161 -> 2
    141-160 -> 6
    111-140 -> 10
    81-110 -> 6
    <80 -> 0
    """
    if wpm >= 161:
        return 2, "Too fast"
    if 141 <= wpm < 161:
        return 6, "Fast"
    if 111 <= wpm < 141:
        return 10, "Ideal"
    if 81 <= wpm < 111:
        return 6, "Slow"
    return 0, "Too slow"

def _count_grammar_errors(text):
    """
    Use language_tool_python if available to count grammar rule violations per 100 words.
    If not available, use a simple heuristic: detect multiple common error patterns (very rough).
    Returns errors_per_100_words (float)
    """
    wc = _word_count(text)
    if wc == 0:
        return 0.0, "No words"
    if _lt_tool is not None:
        matches = _lt_tool.check(text)
        # filter out punctuation-only matches
        errors = 0
        for m in matches:
            # robustly support both rule_id and ruleId names across versions
            rule = getattr(m, "rule_id", None) or getattr(m, "ruleId", None)
            if rule and rule != "WHITESPACE_RULE":
                errors += 1
        per100 = (errors / wc) * 100.0
        return per100, f"{errors} grammar issues detected by language-tool"
    # heuristic fallback: count occurrences of repeated words like "the the", common contractions without apostrophe, simple punctuation errors
    errors = 0
    # repeated words
    repeated = re.findall(r"\b(\w+)\s+\1\b", text.lower())
    errors += len(repeated)
    # simplistic missing apostrophe contractions: e.g., dont, isnt -> count occurrences of common words without apostrophe
    errors += len(re.findall(r"\b(dont|doesnt|isnt|cant|wont|shouldnt|couldnt|wouldnt)\b", text.lower()))
    per100 = (errors / wc) * 100.0
    return per100, f"{errors} heuristic grammar issues (fallback)"

def _score_grammar_errors(per100):
    """
    Map errors per 100 words to grammar points (according rubric section):
    ...
    """
    r = per100 / 100.0
    if r < 0.3:
        return 10
    if r < 0.5:
        return 8
    if r < 0.7:
        return 6
    if r < 0.9:
        return 4
    return 2

def _score_ttr(ttr_val):
    """
    TTR bands:
    ...
    """
    if ttr_val >= 0.9:
        return 10
    if ttr_val >= 0.7:
        return 8
    if ttr_val >= 0.5:
        return 6
    if ttr_val >= 0.3:
        return 4
    return 2

def _filler_rate(text):
    toks = _word_tokens(text)
    if not toks:
        return 0.0, 0
    count = 0
    txt = text.lower()
    for f in _FILLER_WORDS:
        count += len(re.findall(r"\b" + re.escape(f) + r"\b", txt))
    rate = (count / len(toks)) * 100.0
    return rate, count

def _score_filler_rate(filler_pct):
    if filler_pct <= 3.0:
        return 15
    if filler_pct <= 6.0:
        return 12
    if filler_pct <= 9.0:
        return 9
    if filler_pct <= 12.0:
        return 6
    return 3

def _score_sentiment(text):
    if _vader is None:
        val = 0.5
        note = "VADER not available; using neutral fallback"
    else:
        vs = _vader.polarity_scores(text)
        val = (vs.get("compound", 0.0) + 1.0) / 2.0
        note = f"VADER compound raw={vs.get('compound',0.0)}"
    if val >= 0.9:
        points = 15
    elif val >= 0.7:
        points = 12
    elif val >= 0.5:
        points = 9
    elif val >= 0.3:
        points = 6
    else:
        points = 3
    return val, points, note

def compute_scores_for_transcript(text, duration_seconds=None):
    """
    Compute full rubric scores and return (out_dict, df_out)
    out_dict contains overall_score (0-100), word_count, sentence_count, duration_seconds_used and per_criterion list with feedback.
    df_out is a DataFrame for Excel export that now includes sentence count and duration used.
    """
    txt = str(text).strip()
    wc = _word_count(txt)

    # sentence count (simple split by ., !, ? — ignoring empty items)
    sentences = [s.strip() for s in re.split(r'[.!?]+', txt) if s.strip()]
    sentence_count = len(sentences)

    # Use the provided duration_seconds as-is (None if not provided)
    duration_used = None
    try:
        if duration_seconds is not None and str(duration_seconds).strip() != "":
            duration_used = float(duration_seconds)
    except Exception:
        duration_used = None

    # Content & Structure
    sal_score, sal_msg = _compute_salutation_score(txt)  # out of 5
    must_keywords = _CONTENT_KEYWORDS_MUST
    found_keywords = _detect_keywords(txt, must_keywords)
    keyword_hits = len(found_keywords)
    keyword_score_total = min((keyword_hits * 4), 20)  # 4 points each up to 20

    # Flow: 5 points
    flow_score, flow_msg = _compute_flow_score(txt)

    # Semantic bonus (0-10)
    sem_bonus = 0.0
    sem_note = "Semantic model not available or not used."
    model, util = _load_semantic_model()
    if model is not None:
        try:
            emb1 = model.encode(txt, convert_to_tensor=True)
            emb2 = model.encode("Introduction/self introduction content expected", convert_to_tensor=True)
            sim = util.cos_sim(emb1, emb2).item()
            sim_norm = max(0.0, min(1.0, (sim + 1.0) / 2.0))
            sem_bonus = sim_norm * 10.0  # scale to 0-10
            sem_note = f"Semantic similarity normalized={round(sim_norm,3)}"
        except Exception as e:
            sem_bonus = min(10.0, (keyword_hits / len(must_keywords)) * 10.0) if must_keywords else 0.0
            sem_note = f"Semantic compute failed: {e}"
    else:
        sem_bonus = min(10.0, (keyword_hits / len(must_keywords)) * 10.0) if must_keywords else 0.0

    content_structure_score = sal_score + keyword_score_total + flow_score + sem_bonus

    # Speech Rate (10 points)
    wpm = _compute_wpm(wc, duration_used)
    speech_points, speech_msg = _score_speech_rate(wpm)

    # Language & Grammar (20 points = grammar 10 + TTR 10)
    errors_per100, err_note = _count_grammar_errors(txt)
    grammar_points = _score_grammar_errors(errors_per100)
    ttr_val = _ttr(txt)
    ttr_points = _score_ttr(ttr_val)

    # Clarity (15 points) filler rate
    filler_pct, filler_count = _filler_rate(txt)
    clarity_points = _score_filler_rate(filler_pct)

    # Engagement (15 points) sentiment
    sentiment_val, engagement_points, sentiment_note = _score_sentiment(txt)

    per_criteria = []

    per_criteria.append({
        "criterion": "Content & Structure",
        "components": {
            "Salutation (5)": sal_score,
            "Keywords (20)": keyword_score_total,
            "Flow (5)": flow_score,
            "Semantic bonus (0-10)": round(sem_bonus,3)
        },
        "score": round(content_structure_score,3),
        "max_score": 40,
        "feedback": f"{sal_msg}  Keywords found: {', '.join(found_keywords) if found_keywords else 'None'}.  {flow_msg}.  {sem_note}"
    })

    per_criteria.append({
        "criterion": "Speech Rate",
        "components": {"WPM": round(wpm,2), "band_message": speech_msg},
        "score": speech_points,
        "max_score": 10,
        "feedback": f"WPM={round(wpm,2)}. {speech_msg}"
    })

    per_criteria.append({
        "criterion": "Language & Grammar",
        "components": {"Grammar errors per100": round(errors_per100,3), "Grammar points (out of 10)": grammar_points, "TTR": round(ttr_val,3), "TTR points (out of 10)": ttr_points},
        "score": grammar_points + ttr_points,
        "max_score": 20,
        "feedback": f"{err_note}. TTR={round(ttr_val,3)}"
    })

    per_criteria.append({
        "criterion": "Clarity (Filler Rate)",
        "components": {"Filler %": round(filler_pct,3), "Filler count": filler_count},
        "score": clarity_points,
        "max_score": 15,
        "feedback": f"Filler words={filler_count}, filler_percent={round(filler_pct,2)}%"
    })

    per_criteria.append({
        "criterion": "Engagement (Sentiment)",
        "components": {"Sentiment_normalized_0_1": round(sentiment_val,3)},
        "score": engagement_points,
        "max_score": 15,
        "feedback": f"{sentiment_note}"
    })

    # compute overall numeric score
    total_score_attained = sum(p["score"] for p in per_criteria)
    total_possible = sum(p["max_score"] for p in per_criteria)
    overall_pct = (total_score_attained / total_possible) if total_possible > 0 else 0.0
    overall_score = round(overall_pct * 100.0, 2)

    out = {
        "overall_score": overall_score,
        "word_count": wc,
        "sentence_count": sentence_count,
        "duration_seconds_used": duration_used,
        "per_criterion": per_criteria,
        "totals": {
            "attained": total_score_attained,
            "possible": total_possible
        }
    }

    # DataFrame for Excel output
    rows = []
    for p in per_criteria:
        rows.append({
            "Criterion": p["criterion"],
            "Score Attained": p["score"],
            "Max Score": p["max_score"],
            "Feedback": p["feedback"]
        })
    # Append summary rows for sentence count and duration (so they appear in Results sheet)
    rows.append({
        "Criterion": "Sentence Count",
        "Score Attained": sentence_count,
        "Max Score": "",
        "Feedback": ""
    })
    rows.append({
        "Criterion": "Duration Seconds (user-entered)",
        "Score Attained": duration_used if duration_used is not None else "",
        "Max Score": "",
        "Feedback": ""
    })
    rows.append({
        "Criterion": "Overall",
        "Score Attained": total_score_attained,
        "Max Score": total_possible,
        "Feedback": f"Overall percent: {overall_score}"
    })
    df_out = pd.DataFrame(rows)

    return out, df_out
