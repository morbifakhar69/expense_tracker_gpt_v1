
import os
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from dateutil.relativedelta import relativedelta
from datetime import date, datetime
import io

import db
from parsers import parse_revolut, parse_sparkasse, parse_gebuehrenfrei, parse_klarna, parse_unknown, compute_hashes
from pdf_utils import parse_pdf_statement
from categorizer import apply_rules, DEFAULT_CATEGORIES, DEFAULT_SUBCATS

st.set_page_config(page_title="BudgetBuddy", page_icon="💸", layout="wide")

# Simple "user" – unique per browser (for personal use). You can replace with auth if needed.
if "user_id" not in st.session_state:
    st.session_state["user_id"] = st.session_state.get("_cookie_user", os.environ.get("USER","local")) + "-default"
USER = st.session_state["user_id"]
db.init_db(USER)

# Sidebar
st.sidebar.title("BudgetBuddy")
st.sidebar.caption("Upload, categorize, budget, and track — with zero cost hosting.")

page = st.sidebar.radio("Navigation", ["Upload", "Categorize", "Budgets & Income", "Overview", "Category Reports", "Settings"])

# Helpers
def month_range(d: date):
    start = d.replace(day=1)
    end = (start + relativedelta(months=1)) - relativedelta(days=1)
    return start, end

def load_month(year: int, month: int) -> pd.DataFrame:
    rows = db.list_transactions(USER, year, month)
    if not rows:
        return pd.DataFrame(columns=["date","account","merchant","description","amount","currency","category","subcategory","type","source"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df

# Upload Page
if page == "Upload":
    st.header("1) Upload statements")
    st.write("Drop CSV files from Revolut, Sparkasse, Gebührenfrei (Advanzia), Klarna, etc. I’ll normalize and de-duplicate automatically.")

    files_up = st.file_uploader("Upload one or more CSV/PDF files", type=["csv","pdf"], accept_multiple_files=True)
    if files_up:
        total_ins, total_skip = 0, 0
        for f in files_up:
            name = f.name.lower()
            if name.endswith(".pdf"):
                pdf_bytes = f.read()
                parsed = parse_pdf_statement(name, pdf_bytes)
            else:
                df = pd.read_csv(f, sep=None, engine="python")
                if "revolut" in name:
                    parsed = parse_revolut(df)
                elif "sparkasse" in name or "umsatz" in name:
                    parsed = parse_sparkasse(df)
                elif "klarna" in name:
                    parsed = parse_klarna(df)
                elif "gebuehrenfrei" in name or "advanzia" in name or "mastercard" in name:
                    parsed = parse_gebuehrenfrei(df)
                else:
                    parsed = parse_unknown(df)
            parsed = compute_hashes(parsed)
            rows = parsed.to_dict(orient="records")
            ins, skip = db.insert_transactions(USER, rows)
            total_ins += ins
            total_skip += skip
        st.success(f"Imported {total_ins} new rows. Skipped {total_skip} duplicates.")

    st.markdown("---")
    st.subheader("Preview recent")
    today = date.today()
    dfp = load_month(today.year, today.month)
    st.dataframe(dfp.tail(20))

# Categorize Page
if page == "Categorize":
    st.header("2) Categorize your expenses")
    today = date.today()
    y = st.number_input("Year", min_value=2000, max_value=2100, value=today.year)
    m = st.number_input("Month", min_value=1, max_value=12, value=today.month)
    df = load_month(int(y), int(m))
    if df.empty:
        st.info("No transactions for this month yet.")
    else:
        st.write("Use rules to auto-assign categories. Confirm selections to save new rules.")
        user_rules = db.list_rules(USER)
        dfc = apply_rules(df, user_rules)
        st.dataframe(dfc)

        st.markdown("**Create a new rule**")
        col1, col2 = st.columns(2)
        with col1:
            pattern = st.text_input("Pattern (regex; e.g., 'REWE|LIDL')")
            field = st.selectbox("Field to match", ["merchant", "description"])
        with col2:
            category = st.selectbox("Category", DEFAULT_CATEGORIES)
            subcategory = st.text_input("Subcategory (optional)", "")
            priority = st.slider("Priority (lower = stronger)", 1, 200, 100)

        if st.button("Save Rule"):
            if pattern and category:
                db.add_rule(USER, pattern, field, category, subcategory, priority)
                st.success("Rule saved. Re-run categorization to apply.")

# Budgets & Income
if page == "Budgets & Income":
    st.header("3) Budgets & Income")
    today = date.today()
    y = st.number_input("Year", min_value=2000, max_value=2100, value=today.year, key="by")
    m = st.number_input("Month", min_value=1, max_value=12, value=today.month, key="bm")

    budgets = db.get_budgets(USER, int(y), int(m))
    st.subheader("Budgets")
    for cat in DEFAULT_CATEGORIES:
        col1, col2 = st.columns([2,1])
        with col1:
            st.write(cat)
        with col2:
            amt = budgets.get(cat, 0.0)
            new_amt = st.number_input(f"{cat} budget", min_value=0.0, value=float(amt), step=10.0, key=f"b_{cat}")
            if new_amt != amt:
                db.upsert_budget(USER, int(y), int(m), cat, new_amt)

    st.subheader("Income")
    source = st.text_input("Income source", "Salary")
    amt = st.number_input("Amount", min_value=0.0, step=50.0)
    if st.button("Add Income"):
        db.add_income(USER, int(y), int(m), source, amt)
        st.success("Income added.")

# Overview
if page == "Overview":
    st.header("4) Overview report")
    today = date.today()
    y = st.number_input("Year", min_value=2000, max_value=2100, value=today.year, key="oy")
    m = st.number_input("Month", min_value=1, max_value=12, value=today.month, key="om")

    df = load_month(int(y), int(m))
    if df.empty:
        st.info("No data yet for this month.")
    else:
        df_exp = df[df["amount"] < 0].copy()
        df_exp["amount"] = df_exp["amount"].abs()

        spent_by_cat = df_exp.groupby("category", dropna=False)["amount"].sum().reset_index().fillna("Uncategorized")
        budgets = db.get_budgets(USER, int(y), int(m))
        spent_by_cat["budget"] = spent_by_cat["category"].map(lambda c: budgets.get(c, 0.0))
        spent_by_cat["remaining"] = spent_by_cat["budget"] - spent_by_cat["amount"]

        st.subheader("Budget vs Spent")
        chart = alt.Chart(spent_by_cat).mark_bar().encode(
            x=alt.X("category:N", sort="-y", title="Category"),
            y=alt.Y("amount:Q", title="Spent"),
            tooltip=["category","amount","budget","remaining"]
        ).properties(height=400)
        st.altair_chart(chart, use_container_width=True)

        st.subheader("Monthly Summary")
        total_budget = sum(budgets.values())
        total_spent = df_exp["amount"].sum()
        remaining = total_budget - total_spent
        days_in_month = (date(int(y), int(m), 28) + relativedelta(days=4)).replace(day=1) - relativedelta(days=1)
        days_remaining = max((days_in_month.day - date.today().day), 0) if (int(y)==today.year and int(m)==today.month) else 0
        weekly_allowance = (remaining / max(days_remaining, 1)) * 7 if remaining > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total budget", f"{total_budget:,.2f}")
        col2.metric("Spent", f"{total_spent:,.2f}")
        col3.metric("Remaining", f"{remaining:,.2f}")
        col4.metric("Weekly allowance", f"{weekly_allowance:,.2f}")

        st.subheader("Cashflow (income vs expense)")
        df_income = df[df["amount"] > 0].copy()
        df_income["amount"] = df_income["amount"].astype(float)
        df_exp_line = df_exp.copy()
        df_exp_line["amount"] = -df_exp_line["amount"]

        df_line = pd.concat([
            df_income.assign(kind="Income")[["date","amount","kind"]],
            df_exp_line.assign(kind="Expense")[["date","amount","kind"]],
        ]).sort_values("date")

        line = alt.Chart(df_line).mark_line().encode(
            x="date:T",
            y="amount:Q",
            color="kind:N",
            tooltip=["date:T","kind:N","amount:Q"]
        ).properties(height=300)
        st.altair_chart(line, use_container_width=True)

# Category Reports
if page == "Category Reports":
    st.header("5) Deep-dive by category")
    today = date.today()
    y = st.number_input("Year", min_value=2000, max_value=2100, value=today.year, key="cy")
    m = st.number_input("Month", min_value=1, max_value=12, value=today.month, key="cm")

    df = load_month(int(y), int(m))
    if df.empty:
        st.info("No data yet.")
    else:
        cats = ["All"] + sorted([c for c in df["category"].dropna().unique() if c])
        cat = st.selectbox("Category", cats)
        subcats = ["All"]
        if cat != "All":
            subcats += sorted([s for s in df.loc[df["category"]==cat,"subcategory"].dropna().unique() if s])
        sub = st.selectbox("Subcategory", subcats)

        dff = df.copy()
        if cat != "All":
            dff = dff[dff["category"] == cat]
        if sub != "All":
            dff = dff[dff["subcategory"] == sub]

        dff_exp = dff[dff["amount"] < 0].copy()
        if dff_exp.empty:
            st.info("No expenses in selection.")
        else:
            dff_exp["amount"] = dff_exp["amount"].abs()
            st.write(f"{len(dff_exp)} transactions")
            st.dataframe(dff_exp.sort_values("amount", ascending=False))

            by_merch = dff_exp.groupby("merchant", dropna=False)["amount"].sum().reset_index().sort_values("amount", ascending=False)
            bar = alt.Chart(by_merch.head(20)).mark_bar().encode(
                x=alt.X("merchant:N", sort="-y"),
                y="amount:Q",
                tooltip=["merchant","amount"]
            ).properties(height=400)
            st.altair_chart(bar, use_container_width=True)

            trend = alt.Chart(dff_exp).mark_line().encode(
                x="date:T",
                y="amount:Q",
                tooltip=["date:T","amount:Q"]
            ).properties(height=300)
            st.altair_chart(trend, use_container_width=True)

# Settings
if page == "Settings":
    st.header("6) Settings & Backup")
    st.write("Export a full backup of your database, or import one to restore/sync.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Export backup"):
            content = db.export_backup()
            st.download_button("Download backup", data=content, file_name="budgetbuddy.db", mime="application/octet-stream")
    with c2:
        up = st.file_uploader("Import backup", type=["db"])
        if up is not None:
            db.import_backup(up.read())
            st.success("Backup imported.")

    st.markdown("---")
    st.write("**Tips**")
    st.markdown("""
    - To access on iPhone: deploy to Streamlit Community Cloud and open your app URL in Safari/Chrome.
    - If you want automatic syncing between devices, enable the optional Supabase mode in `README.md`.
    - Add rules on the *Categorize* tab so the app learns your merchants.
    """)
