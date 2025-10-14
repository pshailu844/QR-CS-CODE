# QR Request Manager (Streamlit)

A Streamlit app where an admin manages requests, generates QR codes, and viewers scan to open a public form with name, mobile number, and email.

## Features
- Admin password (env `ADMIN_PASSWORD`, default `admin`)
- Create/close/reopen/delete requests
- QR linking to `?view=form&token=...`
- Public form with validation; submissions stored in SQLite

## Setup
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run
```bash
$env:ADMIN_PASSWORD = "your-strong-password"   # optional
$env:APP_DB_PATH = "D:\\data\\qr_app.db"      # optional
streamlit run app.py
```

In the Admin dashboard, set "External Base URL" to your public or LAN URL, e.g. `http://192.168.1.50:8501`.
