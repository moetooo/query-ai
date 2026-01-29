import streamlit as st
import pandas as pd
from main import query

st.set_page_config(page_title="QueryAI", layout="centered")

# dark theme
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stApp { 
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        color: #c9d1d9;
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
    
    code { color: #79c0ff !important; background: #161b22 !important; }
    
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
</style>
""", unsafe_allow_html=True)

# header
st.markdown('<div class="main-title">QueryAI</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Type a question, get SQL results</div>', unsafe_allow_html=True)

# input form
with st.form(key="query_form"):
    question = st.text_input(
        "Query",
        placeholder="Type your question and press Enter...",
        label_visibility="collapsed"
    )
    submitted = st.form_submit_button("Search")

# run query
if submitted and question.strip():
    with st.spinner(""):
        rows, cols_data, sql = query(question)
    
    with st.expander("View SQL", expanded=False):
        st.code(sql, language="sql")
    
    if rows is None:
        st.error("Query failed. Try rephrasing your question.")
    elif len(rows) == 0:
        st.info("No results. Try a broader query.")
    else:
        total = len(rows)
        MAX_DISPLAY = 100
        display_rows = rows[:MAX_DISPLAY] if total > MAX_DISPLAY else rows
        
        st.markdown(f'<p class="result-count">{total} results</p>', unsafe_allow_html=True)
        
        df = pd.DataFrame(display_rows, columns=cols_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        if total > MAX_DISPLAY:
            st.caption(f"Showing first {MAX_DISPLAY} of {total}")
        
        if total > 20:
            full_df = pd.DataFrame(rows, columns=cols_data)
            csv = full_df.to_csv(index=False)
            st.download_button("Download CSV", csv, "results.csv", "text/csv")
