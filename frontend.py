import os
import streamlit as st
import pandas as pd
from main import query

st.set_page_config(page_title="QueryAI", layout="centered")

# dark theme
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    body, .stApp { font-family: 'Inter', sans-serif; }
    
    .stApp { 
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        color: #c9d1d9;
    }

    [data-testid="stSidebar"] {
        background-color: #161b22 !important;
        color: #c9d1d9 !important;
    }
    
    .main-title {
        font-size: 2.5rem;
        font-weight: 600;
        color: #58a6ff;
        margin-bottom: 0.5rem;
    }
    
    .subtitle {
        color: #8b949e;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    
    .stTextInput input {
        background: #21262d !important;
        color: #c9d1d9 !important;
        border: 1px solid #30363d !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        font-size: 1rem !important;
    }
    
    .stTextInput input:focus {
        border-color: #58a6ff !important;
        box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15) !important;
    }
    
    .result-count {
        color: #58a6ff;
        font-weight: 500;
        margin: 1rem 0 0.5rem 0;
    }
    
    .help-text {
        color: #8b949e;
        font-size: 0.9rem;
        margin-top: 1rem;
    }
    
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    
    :not(pre) > code {
        color: #79c0ff !important;
        background: #161b22 !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
    }

    .stCodeBlock, [data-testid="stCodeBlock"] {
        border-radius: 8px !important;
        overflow: hidden !important;
    }

    .stCodeBlock pre {
        padding: 16px 20px !important;
        margin: 0 !important;
        background: #161b22 !important;
    }
    
    .stButton button {
        background: #238636 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 8px 20px !important;
        font-weight: 500 !important;
    }
    
    .stButton button:hover {
        background: #2ea043 !important;
    }

    .stDownloadButton button {
        background: #21262d !important;
        color: #c9d1d9 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
        padding: 6px 16px !important;
        font-weight: 500 !important;
    }

    .stDownloadButton button:hover {
        background: #30363d !important;
        border-color: #8b949e !important;
    }
</style>
""", unsafe_allow_html=True)

# sidebar configuration and tips
with st.sidebar:
    st.header("Settings")
    current_key = os.getenv("GROQ_API_KEY", "")
    api_key_input = st.text_input(
        "Groq API Key",
        value=current_key,
        type="password",
        placeholder="gsk_...",
        help="Enter your Groq API key or set GROQ_API_KEY in .env"
    )
    if api_key_input:
        os.environ["GROQ_API_KEY"] = api_key_input

    st.markdown("---")
    st.markdown("### 🔄 Auto Model Failover")
    st.caption(
        "Queries automatically attempt the highest-volume models first and cascade down on errors:\n\n"
        "1. **`llama-3.1-8b-instant`** (14.4k queries/day)\n"
        "2. **`llama-3.3-70b-versatile`**\n"
        "3. **`gemma2-9b-it`**\n"
        "4. **`llama-3.2-3b-preview`**\n"
        "5. **`llama-3.2-1b-preview`**"
    )

    st.markdown("---")
    st.markdown("### Example Questions")
    st.markdown("- *Show all customers*")
    st.markdown("- *List all products in Electronics category*")
    st.markdown("- *What are the top 5 highest order totals?*")
    st.markdown("- *How many orders did Alice Johnson place?*")

# header
st.markdown('<div class="main-title">QueryAI</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Type a question, get SQL results</div>', unsafe_allow_html=True)

# input form
with st.form(key="query_form"):
    question = st.text_input(
        "Query",
        placeholder="Type your question and press Enter... (e.g. Show all products)",
        label_visibility="collapsed"
    )
    submitted = st.form_submit_button("Search")

# run query
if submitted:
    if not question.strip():
        st.warning("Please enter a question to query the database.")
    else:
        with st.spinner("Generating SQL and running query..."):
            rows, cols_data, sql, model_used = query(question)
        
        if rows is None:
            st.error(sql)
            if "GROQ_API_KEY" in sql:
                st.info("Tip: You can enter your Groq API key in the sidebar Settings.")
        elif len(rows) == 0:
            st.info("No results. Try a broader query.")
        else:
            total = len(rows)
            MAX_DISPLAY = 100
            display_rows = rows[:MAX_DISPLAY] if total > MAX_DISPLAY else rows
            
            st.markdown(f'<p class="result-count">{total} result{"s" if total != 1 else ""}</p>', unsafe_allow_html=True)
            
            df = pd.DataFrame(display_rows, columns=cols_data)
            st.dataframe(df, width="stretch", hide_index=True)
            
            if total > MAX_DISPLAY:
                st.caption(f"Showing first {MAX_DISPLAY} of {total}")
            
            full_df = pd.DataFrame(rows, columns=cols_data)
            csv = full_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="results.csv",
                mime="text/csv"
            )
        
        if sql and not sql.startswith("Error:"):
            with st.expander("View SQL", expanded=False):
                st.code(sql, language="sql")
                if model_used:
                    st.caption(f"⚡ Generated via `{model_used}` (Auto-switched)")


