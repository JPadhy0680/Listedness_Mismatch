import os
import json
import tempfile
from datetime import datetime
import streamlit as st
import pandas as pd

# Import from same folder – SIMPLE, 100% reliable
from quality_reviewer import run_qc

st.set_page_config(page_title="Quality Reviewer", layout="wide")
st.title("Quality Reviewer (Source vs Processed XML)")

with st.sidebar:
    st.header("Settings")
    report_format = st.selectbox("Report format", ["all", "xlsx", "csv", "json"])
    gen_html = st.checkbox("Generate HTML summary", value=True)
    outdir_name = st.text_input("Output folder name", value="qc_output")

col1, col2, col3 = st.columns(3)

source_file = col1.file_uploader("Source Document", type=["pdf","docx","txt","csv","xlsx","xls"])
xml_file = col2.file_uploader("Processed XML", type=["xml"])
config_file = col3.file_uploader("Config JSON", type=["json"])

if st.button("Run Quality Check"):
    if not (source_file and xml_file and config_file):
        st.error("Please upload all three files.")
        st.stop()

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, source_file.name)
        with open(src_path, "wb") as f:
            f.write(source_file.read())

        xml_path = os.path.join(tmpdir, xml_file.name)
        with open(xml_path, "wb") as f:
            f.write(xml_file.read())

        cfg_path = os.path.join(tmpdir, config_file.name)
        with open(cfg_path, "wb") as f:
            f.write(config_file.read())

        outdir = os.path.join(tmpdir, outdir_name)

        with st.spinner("Running QC..."):
            try:
                paths = run_qc(src_path, xml_path, cfg_path, outdir, report_format, gen_html)
            except Exception as e:
                st.error("QC failed!")
                st.exception(e)
                st.stop()

        st.success("QC completed!")

        for k, p in paths.items():
            with open(p, "rb") as fh:
                st.download_button(
                    label=f"Download {k.upper()} report",
                    data=fh.read(),
                    file_name=os.path.basename(p)
                )

        if "csv" in paths:
            df = pd.read_csv(paths["csv"])
            st.dataframe(df)
        elif "json" in paths:
            df = pd.read_json(paths["json"])
            st.dataframe(df)
