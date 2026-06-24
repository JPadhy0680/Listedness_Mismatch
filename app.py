import io
import re
from typing import Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="PV Mismatch Finder", layout="wide")

REQUIRED_COLUMNS = [
    "Safety Report ID",
    "Active Ingredients",
    "LLT",
    "PT",
    "SOC",
    "Expectedness",
]

CANONICAL_MAP = {
    "safetyreportid": "Safety Report ID",
    "safety_report_id": "Safety Report ID",
    "activelngredients": "Active Ingredients",  # common OCR typo safeguard
    "activeingredients": "Active Ingredients",
    "active_ingredients": "Active Ingredients",
    "llt": "LLT",
    "pt": "PT",
    "soc": "SOC",
    "expectedness": "Expectedness",
    "expected": "Expectedness",
}


def _clean_header(col: str) -> str:
    c = str(col).strip()
    c = re.sub(r"\s+", " ", c)
    key = re.sub(r"[^a-zA-Z0-9]+", "", c).lower()
    return CANONICAL_MAP.get(key, c)


@st.cache_data(show_spinner=False)
def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        # Try common delimiters
        raw = uploaded_file.getvalue()
        for sep in [",", "\t", ";", "|"]:
            try:
                df = pd.read_csv(io.BytesIO(raw), sep=sep, dtype=str)
                if df.shape[1] > 1:
                    return df
            except Exception:
                pass
        # Fallback: auto-detect separator
        return pd.read_csv(io.BytesIO(raw), sep=None, engine="python", dtype=str)
    elif name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file, engine="openpyxl", dtype=str)
    elif name.endswith(".xls"):
        return pd.read_excel(uploaded_file, engine="xlrd", dtype=str)
    else:
        raise ValueError("Unsupported file type. Please upload CSV/XLSX/XLS.")


@st.cache_data(show_spinner=False)
def read_pasted_text(text: str) -> pd.DataFrame:
    text = text.strip()
    if not text:
        return pd.DataFrame()

    # Prefer tab-separated input (as in your example)
    try:
        df = pd.read_csv(io.StringIO(text), sep="\t", dtype=str)
        if df.shape[1] > 1:
            return df
    except Exception:
        pass

    # Fallback: try commas or multiple spaces
    for sep in [",", r"\s{2,}"]:
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, engine="python", dtype=str)
            if df.shape[1] > 1:
                return df
        except Exception:
            pass

    raise ValueError("Could not parse pasted text. Use tab-separated data or upload a file.")



def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_clean_header(c) for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype(str).fillna("").str.strip()
    # Replace stringified null-like values
    df = df.replace({"nan": "", "None": "", "NaN": ""})
    return df



def validate_columns(df: pd.DataFrame) -> Tuple[bool, list, list]:
    present = list(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    return len(missing) == 0, missing, present



def find_mismatches(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = df.copy()

    # Normalize key fields only for comparison; keep original display values too
    for col in ["Active Ingredients", "PT", "SOC", "Expectedness"]:
        work[f"__norm__{col}"] = (
            work[col]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .str.upper()
        )

    group_cols = ["__norm__Active Ingredients", "__norm__PT"]

    summary = (
        work.groupby(group_cols, dropna=False)
        .agg(
            Molecule=("Active Ingredients", lambda s: sorted(set([x for x in s if str(x).strip()]))),
            PT_display=("PT", lambda s: sorted(set([x for x in s if str(x).strip()]))),
            SOC_values=("SOC", lambda s: sorted(set([x for x in s if str(x).strip()]))),
            Expectedness_values=("Expectedness", lambda s: sorted(set([x for x in s if str(x).strip()]))),
            Safety_Report_IDs=("Safety Report ID", lambda s: sorted(set([x for x in s if str(x).strip()]))),
            Row_Count=("PT", "size"),
        )
        .reset_index()
    )

    summary["SOC_Unique_Count"] = summary["SOC_values"].apply(len)
    summary["Expectedness_Unique_Count"] = summary["Expectedness_values"].apply(len)
    summary["SOC_Mismatch"] = summary["SOC_Unique_Count"] > 1
    summary["Expectedness_Mismatch"] = summary["Expectedness_Unique_Count"] > 1
    summary["Mismatch_Type"] = summary.apply(
        lambda r: "Both SOC & Expectedness"
        if r["SOC_Mismatch"] and r["Expectedness_Mismatch"]
        else ("SOC only" if r["SOC_Mismatch"] else ("Expectedness only" if r["Expectedness_Mismatch"] else "")),
        axis=1,
    )

    mismatch_summary = summary[(summary["SOC_Mismatch"]) | (summary["Expectedness_Mismatch"])].copy()
    if mismatch_summary.empty:
        flagged_rows = work.iloc[0:0].copy()
    else:
        flagged_rows = work.merge(
            mismatch_summary[group_cols + ["Mismatch_Type", "SOC_values", "Expectedness_values"]],
            on=group_cols,
            how="inner",
        )

    # Clean output columns
    detail_cols = [
        "Safety Report ID",
        "Active Ingredients",
        "LLT",
        "PT",
        "SOC",
        "Expectedness",
        "Mismatch_Type",
        "SOC_values",
        "Expectedness_values",
    ]
    flagged_rows = flagged_rows[detail_cols].copy()

    mismatch_summary = mismatch_summary[
        [
            "Molecule",
            "PT_display",
            "SOC_values",
            "Expectedness_values",
            "Safety_Report_IDs",
            "Row_Count",
            "Mismatch_Type",
        ]
    ].copy()

    # Convert lists to readable strings for display/export
    def stringify_list(x):
        if isinstance(x, list):
            return " | ".join(map(str, x))
        return x

    for col in flagged_rows.columns:
        flagged_rows[col] = flagged_rows[col].apply(stringify_list)
    for col in mismatch_summary.columns:
        mismatch_summary[col] = mismatch_summary[col].apply(stringify_list)

    if flagged_rows.empty:
        clean_rows = df.copy()
    else:
        flagged_ids = set(flagged_rows["Safety Report ID"].astype(str))
        clean_rows = df[~df["Safety Report ID"].astype(str).isin(flagged_ids)].copy()

    return mismatch_summary, flagged_rows, clean_rows



def to_excel_bytes(summary_df: pd.DataFrame, details_df: pd.DataFrame, clean_df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Mismatch Summary")
        details_df.to_excel(writer, index=False, sheet_name="Flagged Rows")
        clean_df.to_excel(writer, index=False, sheet_name="No Mismatch Rows")
    output.seek(0)
    return output.getvalue()


st.title("PV Mismatch Finder")
st.caption(
    "Find records where the same Active Ingredient + PT have different SOC and/or Expectedness."
)

with st.expander("Expected input format", expanded=False):
    st.markdown(
        """
        Required columns:
        - **Safety Report ID**
        - **Active Ingredients**
        - **LLT**
        - **PT**
        - **SOC**
        - **Expectedness**

        Example:
        ```text
        Safety Report ID\tActive Ingredients\tLLT\tPT\tSOC\tExpectedness
        GB-CELIXP-000330-01\tAPIXABAN\tAnal bleeding (10049563)\tAnal haemorrhage (10049555)\tGastrointestinal disorders (10017947)\tUNITED KINGDOM-SmPC-Expected
        GB-CELIXP-001438-01\tAPIXABAN\tAnal bleeding (10049563)\tAnal haemorrhage (10049555)\tGastrointestinal disorders (10017947)\tUNITED KINGDOM-SmPC-Unexpected
        ```
        """
    )

source = st.radio("Choose input method", ["Upload file", "Paste data"], horizontal=True)
raw_df: Optional[pd.DataFrame] = None

if source == "Upload file":
    uploaded_file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])
    if uploaded_file is not None:
        try:
            raw_df = read_uploaded_file(uploaded_file)
        except Exception as e:
            st.error(f"Error reading file: {e}")
else:
    pasted = st.text_area(
        "Paste tabular data here",
        height=240,
        placeholder="Paste tab-separated data with headers...",
    )
    if pasted.strip():
        try:
            raw_df = read_pasted_text(pasted)
        except Exception as e:
            st.error(f"Error parsing pasted text: {e}")

if raw_df is not None and not raw_df.empty:
    df = standardize_dataframe(raw_df)
    valid, missing_cols, present_cols = validate_columns(df)

    st.subheader("Preview")
    st.dataframe(df.head(20), use_container_width=True)

    if not valid:
        st.error(
            "Missing required columns: " + ", ".join(missing_cols) +
            "\n\nDetected columns: " + ", ".join(present_cols)
        )
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            ignore_case = st.checkbox("Ignore case while comparing", value=True, disabled=True)
        with col2:
            trim_spaces = st.checkbox("Trim extra spaces while comparing", value=True, disabled=True)
        with col3:
            run = st.button("Find Mismatches", type="primary", use_container_width=True)

        if run:
            summary_df, details_df, clean_df = find_mismatches(df)

            st.subheader("Results")
            m1, m2, m3 = st.columns(3)
            m1.metric("Total rows", len(df))
            m2.metric("Mismatch groups", len(summary_df))
            m3.metric("Flagged rows", len(details_df))

            tabs = st.tabs(["Mismatch Summary", "Flagged Rows", "No Mismatch Rows"])
            with tabs[0]:
                if summary_df.empty:
                    st.success("No mismatch found. For each Active Ingredient + PT, SOC and Expectedness are consistent.")
                else:
                    st.dataframe(summary_df, use_container_width=True)
            with tabs[1]:
                if details_df.empty:
                    st.info("No flagged rows.")
                else:
                    st.dataframe(details_df, use_container_width=True)
            with tabs[2]:
                st.dataframe(clean_df, use_container_width=True)

            excel_bytes = to_excel_bytes(summary_df, details_df, clean_df)
            csv_bytes = details_df.to_csv(index=False).encode("utf-8")

            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    "Download flagged rows (CSV)",
                    data=csv_bytes,
                    file_name="pv_flagged_rows.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with d2:
                st.download_button(
                    "Download full result (Excel)",
                    data=excel_bytes,
                    file_name="pv_mismatch_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
else:
    st.info("Upload a file or paste your data to begin.")
