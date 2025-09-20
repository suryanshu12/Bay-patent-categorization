import sqlite3
import pandas as pd
import streamlit as st
from openai import OpenAI
import re
from dotenv import load_dotenv
import os

# -------------------- Config --------------------
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
    """Automatically append patent data to user instructions."""
    return f"""
{user_prompt}

Patent Number: {patent.get('Patent_Number', '')}
Title: {patent.get('Title', '')}
Abstract: {patent.get('Abstract', '')}
Claims: {patent.get('Claims', '')}
Description: {patent.get('Description', '')}
"""

def summarize_patent(patent: dict, instruction_prompt: str) -> str:
    """Use GPT to summarize a single patent."""
    final_prompt = build_final_prompt(instruction_prompt, patent)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert patent analyst."},
            {"role": "user", "content": final_prompt}
        ]
    )

    return response.choices[0].message.content.strip()

def parse_summary(summary: str) -> dict:
    data = {"Industry Domain": "", "Technology Area": "", "Sub-Technology Area": "", "Keywords": ""}
    patterns = {
        "Industry Domain": r"Industry Domain:\s*(.*)",
        "Technology Area": r"Technology Area:\s*(.*)",
        "Sub-Technology Area": r"Sub-Technology Area:\s*(.*)",
        "Keywords": r"Keywords:\s*(.*)"
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, summary, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()
    return data

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

        st.caption("✏️ This will always include Title, Abstract, Claims, and Description automatically.")

    # Patent input box
    search_patents = st.text_input("Enter Patent Numbers (comma separated)", "")

    if search_patents:
        numbers = [n.strip() for n in search_patents.split(",") if n.strip()]
        results = get_patents_by_numbers(numbers)

        if results:
            export_data = []
            for idx, patent in enumerate(results, start=1):
                st.markdown(f"## 📑 Patent {idx}: {patent['Patent_Number']}")
                with st.spinner(f"Summarizing {patent['Patent_Number']}..."):
                    summary = summarize_patent(patent, instruction_prompt)
                    parsed = parse_summary(summary)

                st.markdown("### 💡 AI Summary")
                st.write(summary)

                st.markdown("### 📜 Patent Details")
                st.write(f"**Title:** {patent['Title']}")
                st.write(f"**Abstract:** {patent['Abstract']}")
                st.markdown("---")

                export_data.append({
                    "Patent Number": patent['Patent_Number'],
                    "Title": patent['Title'],
                    "Abstract": patent['Abstract'],
                    "Industry Domain": parsed["Industry Domain"],
                    "Technology Area": parsed["Technology Area"],
                    "Sub-Technology Area": parsed["Sub-Technology Area"],
                    "Keywords": parsed["Keywords"]
                })

            if export_data:
                df_export = pd.DataFrame(export_data)
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

