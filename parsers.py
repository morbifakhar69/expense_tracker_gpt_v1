
import pandas as pd
import numpy as np
import hashlib
from dateutil import parser as dparser

def _normalize_amount(x):
    if isinstance(x, str):
        x = x.replace("€", "").replace(",", ".").replace(" ", "")
    try:
        return float(x)
    except Exception:
        return np.nan

def _hash_row(row: pd.Series) -> str:
    s = "|".join(str(row.get(k,"")) for k in ["date","account","merchant","description","amount","currency","type","source"])
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def parse_revolut(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("completed date") or cols.get("date") or list(df.columns)[0]
    desc_col = cols.get("description") or cols.get("reference") or list(df.columns)[1]
    amt_col = cols.get("amount") or cols.get("value") or list(df.columns)[2]
    cur_col = cols.get("currency") or cols.get("currencies currency") or "Currency"
    type_col = cols.get("type") or "Type"
    acc = "Revolut"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col].apply(lambda x: dparser.parse(str(x)).date())),
        "account": acc,
        "merchant": df[desc_col].astype(str).str.extract(r"^([^-,|]+)")[0].fillna(df[desc_col].astype(str)),
        "description": df[desc_col].astype(str),
        "amount": df[amt_col].apply(_normalize_amount),
        "currency": df.get(cur_col, pd.Series(["EUR"]*len(df))),
        "type": df.get(type_col, pd.Series(["card"]*len(df))).astype(str),
        "source": pd.Series(["Revolut"]*len(df))
    })
    return out

def parse_sparkasse(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("buchungstag") or cols.get("wertstellung") or list(df.columns)[0]
    desc_col = cols.get("verwendungszweck") or cols.get("text") or list(df.columns)[1]
    amt_col = cols.get("betrag") or list(df.columns)[2]
    cur_col = cols.get("währung") or "Währung"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col].apply(lambda x: dparser.parse(str(x)).date())),
        "account": "Sparkasse",
        "merchant": df[desc_col].astype(str).str.extract(r"^([^-,|]+)")[0].fillna(df[desc_col].astype(str)),
        "description": df[desc_col].astype(str),
        "amount": df[amt_col].apply(_normalize_amount),
        "currency": df.get(cur_col, pd.Series(["EUR"]*len(df))),
        "type": pd.Series(["bank"]*len(df)),
        "source": pd.Series(["Sparkasse"]*len(df))
    })
    return out

def parse_gebuehrenfrei(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("datum") or cols.get("date") or list(df.columns)[0]
    desc_col = cols.get("buchungstext") or cols.get("beschreibung") or list(df.columns)[1]
    amt_col = cols.get("betrag") or cols.get("amount") or list(df.columns)[2]
    cur_col = cols.get("währung") or cols.get("currency") or "Währung"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col].apply(lambda x: dparser.parse(str(x)).date())),
        "account": "Gebührenfrei",
        "merchant": df[desc_col].astype(str).str.extract(r"^([^-,|]+)")[0].fillna(df[desc_col].astype(str)),
        "description": df[desc_col].astype(str),
        "amount": df[amt_col].apply(_normalize_amount),
        "currency": df.get(cur_col, pd.Series(["EUR"]*len(df))),
        "type": pd.Series(["card"]*len(df)),
        "source": pd.Series(["Gebuehrenfrei"]*len(df))
    })
    return out

def parse_klarna(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("date") or cols.get("datum") or list(df.columns)[0]
    merch_col = cols.get("merchant") or cols.get("händler") or cols.get("shop") or list(df.columns)[1]
    desc_col = cols.get("reference") or cols.get("beschreibung") or merch_col
    amt_col = cols.get("amount") or cols.get("betrag") or list(df.columns)[2]
    cur_col = cols.get("currency") or cols.get("währung") or "Currency"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col].apply(lambda x: dparser.parse(str(x)).date())),
        "account": "Klarna",
        "merchant": df[merch_col].astype(str),
        "description": df[desc_col].astype(str),
        "amount": df[amt_col].apply(_normalize_amount),
        "currency": df.get(cur_col, pd.Series(["EUR"]*len(df))),
        "type": pd.Series(["bnpl"]*len(df)),
        "source": pd.Series(["Klarna"]*len(df))
    })
    return out

def parse_unknown(df: pd.DataFrame) -> pd.DataFrame:
    c = {x.lower(): x for x in df.columns}
    date_col = c.get("date") or c.get("datum") or c.get("buchungstag") or list(df.columns)[0]
    desc_col = c.get("description") or c.get("verwendungszweck") or c.get("buchungstext") or list(df.columns)[1]
    amt_col = c.get("amount") or c.get("betrag") or list(df.columns)[2]
    curr_col = c.get("currency") or c.get("währung") or "currency"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col].apply(lambda x: dparser.parse(str(x)).date()), errors="coerce"),
        "account": pd.Series(["Unknown"]*len(df)),
        "merchant": df[desc_col].astype(str).str.extract(r"^([^-,|]+)")[0].fillna(df[desc_col].astype(str)),
        "description": df[desc_col].astype(str),
        "amount": df[amt_col].apply(_normalize_amount),
        "currency": df.get(curr_col, pd.Series(["EUR"]*len(df))),
        "type": pd.Series(["unknown"]*len(df)),
        "source": pd.Series(["Unknown"]*len(df))
    })
    return out

def compute_hashes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["raw_hash"] = df.apply(_hash_row, axis=1)
    return df
