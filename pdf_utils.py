
import io
import re
import pandas as pd
import pdfplumber
from typing import List, Tuple, Optional
from dateutil import parser as dparser

# Optional OCR fallback
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

DATE_PAT = re.compile(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b")

def _clean_amount(s: str) -> Optional[float]:
    if s is None:
        return None
    s = str(s).strip()
    # Normalize German/Euro formatting
    s = s.replace("€", "").replace(" ", "")
    # Handle German decimals "1.234,56" -> "1234.56"
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _try_parse_date(s: str) -> Optional[str]:
    try:
        return dparser.parse(s, dayfirst=True).date().isoformat()
    except Exception:
        return None

def _table_to_df(table_rows: List[List[str]]) -> pd.DataFrame:
    # Heuristic: pick likely columns as date / description / amount / currency
    # Many bank PDFs export tables with headers; we attempt to detect.
    df = pd.DataFrame(table_rows).replace({None: "", pd.NA: ""}).fillna("")
    # Remove entirely empty rows
    df = df[~(df.apply(lambda r: "".join(map(str, r.values)).strip(), axis=1) == "")]
    if df.empty:
        return pd.DataFrame(columns=["date","account","merchant","description","amount","currency","type","source"])

    # Find a date column by regex hit frequency
    date_col = None
    max_hits = -1
    for c in df.columns:
        hits = df[c].astype(str).str.contains(DATE_PAT).sum()
        if hits > max_hits:
            max_hits = hits
            date_col = c
    # Find an amount column (numeric-looking, with many +/- or commas)
    amt_col = None
    max_num = -1
    for c in df.columns:
        nums = 0
        for v in df[c].astype(str).values:
            if _clean_amount(v) is not None:
                nums += 1
        if nums > max_num:
            max_num = nums
            amt_col = c

    # Pick description as the "widest" text column not equal to date/amount
    desc_col = None
    best_len = -1
    for c in df.columns:
        if c in (date_col, amt_col):
            continue
        avg_len = df[c].astype(str).map(len).mean()
        if avg_len > best_len:
            best_len = avg_len
            desc_col = c

    out = pd.DataFrame({
        "date": df[date_col].astype(str).map(_try_parse_date) if date_col is not None else None,
        "account": "",
        "merchant": df[desc_col].astype(str).str.extract(r"^([^-,|]+)")[0] if desc_col is not None else "",
        "description": df[desc_col].astype(str) if desc_col is not None else "",
        "amount": df[amt_col].astype(str).map(_clean_amount) if amt_col is not None else None,
        "currency": "EUR",
        "type": "bank",
        "source": "PDF"
    })
    # Drop rows with no date or no amount
    out = out.dropna(subset=["date","amount"])
    return out

def extract_tables_pdf(file_bytes: bytes) -> List[pd.DataFrame]:
    """Extract tables from a PDF using pdfplumber, return list of DataFrames (one per page table)."""
    dfs = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Try table extraction
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_tolerance": 5
            })
            if not tables:
                # Try looser extraction
                tables = page.extract_tables()
            for t in tables or []:
                # Convert rows to dataframe via heuristic
                df = _table_to_df(t)
                if not df.empty:
                    dfs.append(df)
    return dfs

def ocr_lines_from_pdf(file_bytes: bytes) -> List[str]:
    """Fallback: OCR each page to text, split into lines."""
    if not OCR_AVAILABLE:
        return []
    lines = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Rasterize page
            img = page.to_image(resolution=200).original
            if img.mode != "RGB":
                img = img.convert("RGB")
            text = pytesseract.image_to_string(img, lang="deu+eng")
            for ln in text.splitlines():
                s = ln.strip()
                if s:
                    lines.append(s)
    return lines

def lines_to_df(lines: List[str]) -> pd.DataFrame:
    """Heuristic: parse lines that look like 'DD.MM.YYYY ... amount EUR'."""
    rows = []
    for ln in lines:
        # Find date
        m = DATE_PAT.search(ln)
        if not m:
            continue
        d = _try_parse_date(m.group(1))
        if not d:
            continue
        # Find amount at the end or near end
        parts = ln[m.end():].strip()
        # Try to find a trailing number
        m2 = re.search(r"(-?\d[\d\.\s]*,\d{2}|\d+\.\d{2}|\d+)", parts)
        amt = _clean_amount(m2.group(1)) if m2 else None
        if amt is None:
            continue
        desc = parts
        rows.append((d, desc, amt))
    if not rows:
        return pd.DataFrame(columns=["date","account","merchant","description","amount","currency","type","source"])
    df = pd.DataFrame(rows, columns=["date","description","amount"])
    df["account"] = ""
    df["merchant"] = df["description"].astype(str).str.extract(r"^([^-,|]+)")[0]
    df["currency"] = "EUR"
    df["type"] = "bank"
    df["source"] = "PDF_OCR"
    return df

def parse_pdf_statement(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """
    High-level parser:
    1) Try structured tables with pdfplumber
    2) If empty, try OCR fallback and heuristic line parsing
    3) Return a unified DataFrame in the common schema
    """
    dfs = extract_tables_pdf(file_bytes)
    if dfs:
        out = pd.concat(dfs, ignore_index=True)
        # Attach account/source from filename hints
        name = file_name.lower()
        if "revolut" in name:
            out["account"] = "Revolut"
            out["source"] = "Revolut-PDF"
        elif "sparkasse" in name:
            out["account"] = "Sparkasse"
            out["source"] = "Sparkasse-PDF"
        elif "gebuehrenfrei" in name or "advanzia" in name:
            out["account"] = "Gebührenfrei"
            out["source"] = "Gebuehrenfrei-PDF"
        elif "klarna" in name:
            out["account"] = "Klarna"
            out["source"] = "Klarna-PDF"
        return out

    # Fallback OCR
    lines = ocr_lines_from_pdf(file_bytes)
    if lines:
        df = lines_to_df(lines)
        name = file_name.lower()
        if "revolut" in name:
            df["account"] = "Revolut"
            df["source"] = "Revolut-PDF"
        elif "sparkasse" in name:
            df["account"] = "Sparkasse"
            df["source"] = "Sparkasse-PDF"
        elif "gebuehrenfrei" in name or "advanzia" in name:
            df["account"] = "Gebührenfrei"
            df["source"] = "Gebuehrenfrei-PDF"
        elif "klarna" in name:
            df["account"] = "Klarna"
            df["source"] = "Klarna-PDF"
        return df

    # If nothing works, return empty DF
    return pd.DataFrame(columns=["date","account","merchant","description","amount","currency","category","subcategory","type","source"])
