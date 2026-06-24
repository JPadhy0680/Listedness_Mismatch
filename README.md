# PV Mismatch Finder (Streamlit)

This app finds **mismatches** where the same **Active Ingredients + PT** combination has:
- different **SOC**, and/or
- different **Expectedness**

## Input columns
- Safety Report ID
- Active Ingredients
- LLT
- PT
- SOC
- Expectedness

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Supported input
- CSV
- XLSX / XLS
- Pasted tab-separated data
