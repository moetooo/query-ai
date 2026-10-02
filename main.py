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


def make_sql(schema: str, question: str) -> str:
    """Turn a question into SQL using Groq."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        # Try streamlit secrets
        try:
            import streamlit as st
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass
    
    if not api_key:
        return "Error: GROQ_API_KEY not set. Please set it in your .env file, Streamlit secrets, or sidebar."
    
    try:
        client = Groq(api_key=api_key)
        
        system = """You are a SQL generator. Given the schema and question, write a SQL query.
Use only the tables and columns from the schema. Return ONLY the SQL, nothing else."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
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
            return f"Error: Only read-only SELECT queries are allowed. Attempted:\n{sql}"

        for keyword in FORBIDDEN_KEYWORDS:
            if keyword in upper_sql:
                return f"Error: Forbidden keyword '{keyword.strip()}' found. Only read-only SELECT queries are allowed."

        return sql
    except Exception as err:
        return f"Error communicating with Groq API: {err}"


def query(question: str) -> Tuple[Optional[List[Tuple[Any, ...]]], List[str], str]:
    """Run a natural language query and return (rows, columns, sql)."""
    if not os.path.exists(DB_PATH):
        return None, [], f"Error: Database file '{DB_PATH}' does not exist. Please run create_database.py first."

    schema = get_schema()
    sql = make_sql(schema, question)
    
    if sql.startswith("Error:"):
        return None, [], sql
    
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
    
    return rows, cols, sql


