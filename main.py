from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
import json
import os
import sqlite3

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "amazon.db")
DB_URL = f"sqlite:///{DB_PATH.replace(os.sep, '/')}"


def get_schema():
    """Get table and column info from the database."""
    if not os.path.exists(DB_PATH):
        return "{}"
    engine = create_engine(DB_URL)
    try:
        inspector = inspect(engine)
        tables = {}
        for tbl in inspector.get_table_names():
            cols = inspector.get_columns(tbl)
            tables[tbl] = [c['name'] for c in cols]
        return json.dumps(tables)
    finally:
        engine.dispose()


from groq import Groq


def make_sql(schema, question):
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
        
        sql = resp.choices[0].message.content.strip()
        # clean markdown if present
        sql = sql.replace("```sql", "").replace("```", "").strip()
        return sql
    except Exception as err:
        return f"Error communicating with Groq API: {err}"


def query(question):
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

