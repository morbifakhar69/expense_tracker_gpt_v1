# BudgetBuddy — Streamlit Expense & Budgeting App

A zero-cost, low-maintenance budgeting app you can deploy to Streamlit Community Cloud.  
Works from any device (MacBook, iPhone via Safari/Chrome) and supports CSV uploads from multiple banks (Revolut, Sparkasse, Gebührenfrei/Advanzia, Klarna, etc.).

## Features
- Upload CSVs from different banks. Built-in parsers for Revolut, Sparkasse, Gebührenfrei (Advanzia MC) & Klarna.
- Automatic schema normalization: `date, account, merchant, description, amount, currency, category, subcategory, type, source`.
- Smart rule-based categorization (editable). Learn-as-you-go: confirm categories to save rules.
- Budgets per category + track incomes. Monthly/Yearly views.
- Overview report: budget vs spent, remaining, and weekly allowance.
- Deep-dive report: per-category visuals, filter subcategories, time-series trends.
- Local persistence with SQLite; export/import full backup.
- Optional cloud sync (Supabase) — instructions included below.

## Quickstart (Local / Easiest)
1. Clone/download these files.
2. Create a virtual env and install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   streamlit run app.py
   ```
4. Open the URL that appears in your terminal. On iPhone, use the same URL on the same network or deploy to Streamlit Cloud.

## Deploy to Streamlit Community Cloud (Free)
1. Push this folder to a public GitHub repo.
2. Go to https://share.streamlit.io and deploy the repo; set `app.py` as the entry point.
3. The free tier will keep your app online. For persistence, the included SQLite database file is created in the app's working directory;
   Streamlit Cloud typically persists it between restarts, but not guaranteed. For guaranteed persistence and multi-device syncing,
   enable Supabase (below).

## Optional: Enable Supabase Cloud Sync
1. Create a free project at https://supabase.com/ and get your `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
2. In Streamlit, add Secrets (Settings → Secrets):
   ```toml
   SUPABASE_URL = "https://YOUR.supabase.co"
   SUPABASE_SERVICE_KEY = "YOUR_SERVICE_ROLE_KEY"
   USE_SUPABASE = "true"
   ```
3. Run the migration SQL in Supabase (see `supabase_schema.sql` to be added if you want cloud mode).
4. The app will switch from SQLite to Supabase automatically when `USE_SUPABASE=true`.
   (Note: This template is shipped with SQLite enabled. Cloud mode hook points are in `db.py`.)

## CSV Formats Supported (Out of the box)
- **Revolut**: columns like `Completed Date`, `Description`, `Amount`, `Currency`, `Type`.
- **Sparkasse**: columns like `Buchungstag`, `Verwendungszweck`, `Betrag`, `Währung`.
- **Gebührenfrei (Advanzia MC)**: typical Mastercard CSV/Excel with `Datum`, `Buchungstext`, `Betrag`.
- **Klarna**: exports with `Date`, `Merchant`, `Amount`, `Currency`, `Reference`.

If a format isn't recognized, the app will offer a manual column-mapping dialog and remember your choice for next time.

## Backups
- Use the **Settings → Export Backup** to download the SQLite DB snapshot.
- Use **Settings → Import Backup** to restore on another device — instant sync without cloud.

## Privacy
- Your data stays in your DB. No third-party APIs are contacted unless you enable optional FX rates (off by default) or Supabase.

## PDF Support
- You can upload **PDF statements**. The app first tries to extract tables with `pdfplumber`.
- If the PDF is a **scanned image**, it will optionally attempt OCR with `pytesseract` (works best when running locally with Tesseract installed).
- On Streamlit Cloud, OCR may be unavailable; table-based PDFs still work.
- Parsed rows are normalized into the same schema and deduplicated.
