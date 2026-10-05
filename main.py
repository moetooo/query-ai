import json
import os
import re
import sqlite3
from typing import Any, List, Optional, Tuple
from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import create_engine, inspect

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "amazon.db")
DB_URL = f"sqlite:///{DB_PATH.replace(os.sep, '/')}"

FORBIDDEN_KEYWORDS = (
    "DROP ", "DELETE ", "UPDATE ", "INSERT ",
    "ALTER ", "TRUNCATE ", "CREATE ", "ATTACH ", "DETACH "
)


def get_schema() -> str:
    """Get rich table, column type, and relationship info from the database."""
    if not os.path.exists(DB_PATH):
        return "{}"
    engine = create_engine(DB_URL)
    try:
        inspector = inspect(engine)
        tables = {}
        for tbl in inspector.get_table_names():
            cols = inspector.get_columns(tbl)
            fks = inspector.get_foreign_keys(tbl)
            fk_info = [
                f"{','.join(fk['constrained_columns'])} -> {fk['referred_table']}({','.join(fk['referred_columns'])})"
                for fk in fks
                if fk.get("constrained_columns") and fk.get("referred_table")
            ]
            tables[tbl] = {
                "columns": [f"{c['name']} ({c['type']})" for c in cols],
                "foreign_keys": fk_info,
            }
        return json.dumps(tables, indent=2)
    finally:
        engine.dispose()


def clean_sql(raw_sql: str) -> str:
    """Extract and sanitize SQL from LLM response."""
    match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", raw_sql, re.IGNORECASE)
    sql = match.group(1).strip() if match else raw_sql.strip()
    sql = sql.strip("`").strip()
    return sql.rstrip(";").strip()


MODEL_RANKING = [
    "llama-3.1-8b-instant",     # Rank 1: Highest quota (14,400 RPD), fastest, lowest failure rate
    "llama-3.3-70b-versatile",  # Rank 2: Deep reasoning accuracy
    "gemma2-9b-it",             # Rank 3: High quota backup (14,400 RPD)
    "llama-3.2-3b-preview",     # Rank 4: Lightweight fallback
    "llama-3.2-1b-preview",     # Rank 5: Ultra-lightweight fallback
]


def get_available_models(api_key: Optional[str] = None) -> List[str]:
    """Fetch active chat models available for the Groq API key."""
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GROQ_API_KEY")
            except Exception:
                pass
    if not api_key:
        return []
    try:
        client = Groq(api_key=api_key)
        res = client.models.list()
        chat_models = [
            m.id for m in res.data
            if not any(k in m.id.lower() for k in ["whisper", "guard", "embed", "tts", "transcription"])
        ]
        return chat_models
    except Exception:
        return []


def make_sql(schema: str, question: str) -> Tuple[str, str]:
    """Turn a question into SQL using Groq with automatic top-to-bottom model failover.
    
    Returns:
        Tuple[str, str]: (sql_query, model_name_used)
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass

    if not api_key:
        return "Error: GROQ_API_KEY not set. Please set it in your .env file, Streamlit secrets, or sidebar.", ""

    try:
        client = Groq(api_key=api_key)
    except Exception as init_err:
        return f"Error: Failed to initialize Groq client: {init_err}", ""

    # Fetch live available models for this key
    live_models = get_available_models(api_key=api_key)

    # Build candidate model list ordered by our defined ranking
    candidate_models: List[str] = []
    custom_model = os.getenv("GROQ_MODEL")
    if custom_model:
        candidate_models.append(custom_model)

    for m in MODEL_RANKING:
        if m not in candidate_models:
            if not live_models or m in live_models:
                candidate_models.append(m)

    for m in live_models:
        if m not in candidate_models:
            candidate_models.append(m)

    if not candidate_models:
        candidate_models = list(MODEL_RANKING)

    system = """You are a SQL generator. Given the schema and question, write a SQL query.
Use only the tables and columns from the schema. Return ONLY the SQL, nothing else."""

    attempt_errors = []
    for model_name in candidate_models:
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Schema:\n{schema}\n\nQuestion: {question}\n\nSQL:"}
                ],
                temperature=0
            )

            raw_sql = resp.choices[0].message.content or ""
            sql = clean_sql(raw_sql)

            # Validate that the query is read-only
            upper_sql = sql.upper().strip()
            if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH") or upper_sql.startswith("EXPLAIN")):
                return f"Error: Only read-only SELECT queries are allowed. Attempted:\n{sql}", model_name

            for keyword in FORBIDDEN_KEYWORDS:
                if keyword in upper_sql:
                    return f"Error: Forbidden keyword '{keyword.strip()}' found. Only read-only SELECT queries are allowed.", model_name

            return sql, model_name

        except Exception as err:
            attempt_errors.append(f"{model_name}: {err}")
            # Automatic failover: continue to the next ranked model
            continue

    error_summary = " | ".join(attempt_errors)
    return f"Error: All models in the auto-failover chain failed: {error_summary}", ""


def query(question: str) -> Tuple[Optional[List[Tuple[Any, ...]]], List[str], str, str]:
    """Run a natural language query and return (rows, columns, sql, model_used)."""
    if not os.path.exists(DB_PATH):
        return None, [], f"Error: Database file '{DB_PATH}' does not exist. Please run create_database.py first.", ""

    schema = get_schema()
    sql, model_used = make_sql(schema, question)

    if sql.lower().startswith("error"):
        return None, [], sql, model_used

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description] if cur.description else []
        conn.close()
    except Exception as err:
        rows = None
        cols = []
        sql = f"Error executing query: {err}\n\nSQL attempted:\n{sql}"

    return rows, cols, sql, model_used



