import pandas as pd

def load_rubric(path="Case study for interns.xlsx"):
    """
    Loads the rubric workbook (if present). Returns the first rubric-like sheet as a DataFrame.
    """
    xls = pd.ExcelFile(path, engine="openpyxl")
    # try to find a sheet named 'Rubrics' or similar
    target = None
    for s in xls.sheet_names:
        if 'rubric' in s.lower():
            target = s
            break
    if not target:
        target = xls.sheet_names[0]
    df = pd.read_excel(path, sheet_name=target, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    return df
