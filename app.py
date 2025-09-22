import sqlite3
import pandas as pd
import streamlit as st
from openai import OpenAI
import time
import os
from dotenv import load_dotenv

# -------------------- Config --------------------
load_dotenv()
DB_NAME = "patent.db"
load_dotenv()
OPENAI_API_KEY =os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------- Database Functions --------------------
def create_connection():
    return sqlite3.connect(DB_NAME)

def get_patents_by_numbers(patent_numbers):
    conn = create_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" * len(patent_numbers))
    query = f"""
        SELECT Patent_Number, Title, Abstract, Claims, Description
        FROM patents
        WHERE Patent_Number IN ({placeholders})
    """
    cursor.execute(query, patent_numbers)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "Patent_Number": row[0],
            "Title": row[1],
            "Abstract": row[2],
            "Claims": row[3],
            "Description": row[4],
        }
        for row in rows
    ]

# -------------------- AI Function --------------------
DEFAULT_INSTRUCTION_PROMPT = (
    "You are a patent analyst. Categorize this patent and return only the following fields:\n\n"
    "Industry Domain: ...\n"
    "Technology Area: ...\n"
    "Sub-Technology Area: ...\n"
    "Keywords: (comma-separated technology keywords)"
)

def build_final_prompt(user_prompt, patent):
    return f"""
{user_prompt}

Patent Number: {patent.get('Patent_Number', '')}
Title: {patent.get('Title', '')}
Abstract: {patent.get('Abstract', '')}
Claims: {patent.get('Claims', '')}
Description: {patent.get('Description', '')}
"""

def summarize_patent(patent: dict, instruction_prompt: str) -> str:
    final_prompt = build_final_prompt(instruction_prompt, patent)

    for attempt in range(5):  # retry on rate limits
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert patent analyst."},
                    {"role": "user", "content": final_prompt}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "rate_limit" in str(e).lower():
                wait_time = 2 ** attempt
                st.warning(f"⚠️ Rate limit hit. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e
    st.error("❌ Max retries exceeded.")
    return ""

def parse_dynamic_summary(summary: str) -> dict:
    """Parse GPT output dynamically into key-value pairs."""
    parsed = {}
    for line in summary.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip()] = value.strip()
    return parsed

# -------------------- Streamlit UI --------------------
def main():
    st.title("BAY Patent Search + AI Categorization")

    # Sidebar for custom prompt
    with st.sidebar:
        st.markdown("### 📌 Prompt Settings")
        if "instruction_prompt" not in st.session_state:
            st.session_state["instruction_prompt"] = DEFAULT_INSTRUCTION_PROMPT

        instruction_prompt = st.text_area(
            "Write your custom instructions:",
            value=st.session_state["instruction_prompt"],
            height=200
        )

        if st.button("🔄 Reset Prompt to Default"):
            st.session_state["instruction_prompt"] = DEFAULT_INSTRUCTION_PROMPT
            st.rerun()

    col1, col2 = st.columns([2, 1])
    with col1:
        search_patents = st.text_input("Enter Patent Numbers (comma separated)", "")
    with col2:
        uploaded_file = st.file_uploader("📂 Upload Excel with Patent Numbers", type=["xlsx", "xls"])

    patent_numbers = []

    if search_patents:
        patent_numbers += [n.strip() for n in search_patents.split(",") if n.strip()]

    if uploaded_file:
        try:
            df_uploaded = pd.read_excel(uploaded_file)
            col_candidates = [c for c in df_uploaded.columns if 'patent no' in c.lower()]
            if col_candidates:
                excel_numbers = df_uploaded[col_candidates[0]].dropna().astype(str).tolist()
                patent_numbers += excel_numbers
            else:
                st.error("❌ Excel file must have a column named 'Patent No.'")
        except Exception as e:
            st.error(f"❌ Failed to read Excel file: {e}")

    if patent_numbers:
        results = get_patents_by_numbers(patent_numbers)
        if results:
            all_fields = []  # store field names dynamically
            export_data = []
            for idx, patent in enumerate(results, start=1):
                st.markdown(f"## 📑 Patent {idx}: {patent['Patent_Number']}")
                with st.spinner(f"Summarizing {patent['Patent_Number']}..."):
                    summary = summarize_patent(patent, instruction_prompt)
                    parsed = parse_dynamic_summary(summary)

                # show exactly what GPT returned
                st.markdown("### 💡 AI Summary")
                for k, v in parsed.items():
                    st.write(f"**{k}:** {v}")
                    if k not in all_fields:
                        all_fields.append(k)

                st.markdown("### 📜 Patent Details")
                st.write(f"**Title:** {patent['Title']}")
                st.write(f"**Abstract:** {patent['Abstract']}")
                st.markdown("---")

                row_data = {
                    "Patent Number": patent['Patent_Number'],
                    "Title": patent['Title'],
                    "Abstract": patent['Abstract']
                }
                row_data.update(parsed)
                export_data.append(row_data)

            if export_data:
                # Build DataFrame with Title & Abstract always first
                ordered_columns = ["Patent Number", "Title", "Abstract"] + all_fields
                df_export = pd.DataFrame(export_data)
                # Reorder columns safely (if some columns missing)
                df_export = df_export[[col for col in ordered_columns if col in df_export.columns]]

                excel_file = "patent_categorization.xlsx"
                df_export.to_excel(excel_file, index=False)

                with open(excel_file, "rb") as f:
                    st.download_button(
                        label="📥 Download Results as Excel",
                        data=f,
                        file_name=excel_file,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        else:
            st.error("❌ Patent(s) not found.")

if __name__ == "__main__":
    main()
