# Labor Market Dashboard — Dynamic Data Wiring (Starter)

This app wires **real** data sources for your "Glassdoor × SocialBlade" dashboard:
- Indeed Job Postings Index (sector, US)
- Indeed Posted Wage Tracker (sector, US)
- JOLTS (hires, layoffs/discharges, separations by industry) via FRED CSV
- OEWS (median compensation by occupation, national)
- Industry–Occupation Matrix (popular industries per SOC)

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

If a source is temporarily unavailable, the app falls back gracefully.
