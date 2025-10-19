
import re
from typing import List, Dict, Any
import pandas as pd

DEFAULT_CATEGORIES = [
    "Housing", "Utilities", "Groceries", "Dining & Cafes", "Transport", "Health",
    "Subscriptions", "Entertainment", "Shopping", "Travel", "Education",
    "Gifts & Charity", "Fees & Interest", "Income", "Other"
]

DEFAULT_SUBCATS = {
    "Transport": ["Public Transport", "Fuel", "Taxi", "Parking"],
    "Shopping": ["Electronics", "Clothing", "Home", "Other"],
    "Dining & Cafes": ["Restaurants", "Coffee", "Delivery"],
    "Subscriptions": ["Streaming", "Cloud", "Apps", "Other"],
    "Utilities": ["Electricity", "Gas", "Water", "Internet", "Mobile"],
}

DEFAULT_RULES = [
    (r"REWE|ALDI|LIDL|EDEKA|NETTO|PENNY", "merchant", "Groceries", "", 50),
    (r"DM |ROSSMANN|MÜLLER", "merchant", "Shopping", "Home", 60),
    (r"UBER|FREE NOW|TAXI", "merchant", "Transport", "Taxi", 50),
    (r"BAHNHOF|DB |DEUTSCHE BAHN|VRR|RMV|VBB", "merchant", "Transport", "Public Transport", 50),
    (r"SPOTIFY|NETFLIX|DISNEY|PRIME VIDEO|YOUTUBE PREMIUM|ICLOUD", "merchant", "Subscriptions", "Streaming", 40),
    (r"KLARNA", "description", "Fees & Interest", "", 40),
    (r"APOTHEKE|PHARMACY|DOCTOR|ARZT", "merchant", "Health", "", 60),
    (r"RENT|MIETE", "description", "Housing", "", 10),
    (r"VODAFONE|TELEKOM|O2|1&1|UNITYMEDIA", "merchant", "Utilities", "Internet", 40),
    (r"E.ON|EON|RWE|VATTENFALL|STADTWERKE", "merchant", "Utilities", "Electricity", 40),
    (r"AMAZON", "merchant", "Shopping", "Other", 70),
    (r"REWE LIEFERSERVICE|FLINK|GORILLAS|WOLT|LIEFERANDO", "merchant", "Dining & Cafes", "Delivery", 50),
    (r"RYANAIR|EASYJET|LUFTHANSA|EUROWINGS", "merchant", "Travel", "", 40),
    (r"GEHALT|SALARY|PAYROLL", "description", "Income", "", 10),
]

def apply_rules(df: pd.DataFrame, user_rules: List[Dict[str, Any]]) -> pd.DataFrame:
    df = df.copy()
    df["category"] = df.get("category", "")
    df["subcategory"] = df.get("subcategory", "")

    rules = sorted(user_rules, key=lambda r: (r.get("priority", 100), r.get("id", 0)))

    def match_and_assign(row):
        text_m = str(row.get("merchant", "")).upper()
        text_d = str(row.get("description", "")).upper()

        for r in rules:
            patt = r["pattern"]
            field = r["field"]
            cat = r["category"]
            sub = r.get("subcategory","")
            if field == "merchant":
                if re.search(patt, text_m, flags=re.I):
                    return cat, sub
            else:
                if re.search(patt, text_d, flags=re.I):
                    return cat, sub

        for patt, field, cat, sub, _prio in DEFAULT_RULES:
            if field == "merchant":
                if re.search(patt, text_m, flags=re.I):
                    return cat, sub
            else:
                if re.search(patt, text_d, flags=re.I):
                    return cat, sub
        return row.get("category",""), row.get("subcategory","")

    cats = df.apply(match_and_assign, axis=1, result_type="expand")
    df["category"] = cats[0]
    df["subcategory"] = cats[1]
    return df
