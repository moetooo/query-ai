from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
import json
import os
import sqlite3

load_dotenv()

DB_PATH = "amazon.db"
DB_URL = f"sqlite:///{DB_PATH}"


def get_schema():
    """Get table and column info from the database."""
    engine = create_engine(DB_URL)
    inspector = inspect(engine)
    
    tables = {}
    for tbl in inspector.get_table_names():
        cols = inspector.get_columns(tbl)
        tables[tbl] = [c['name'] for c in cols]
    
    return json.dumps(tables)


from groq import Groq


def make_sql(schema, question):
    """Turn a question into SQL using Groq."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        # Try streamlit secrets
        try:
            import streamlit as st
            api_key = st.secrets.get("GROQ_API_KEY")
        except:
            pass
    
    if not api_key:
        return "Error: GROQ_API_KEY not set"
    
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


def query(question):
    """Run a natural language query and return (rows, columns, sql)."""
    schema = get_schema()
    sql = make_sql(schema, question)
    
    if sql.startswith("Error:"):
        return None, [], sql
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description] if cur.description else []
    except Exception as err:
        rows = None
        cols = []
        sql = f"Error: {err}\n\nSQL attempted:\n{sql}"
    finally:
        conn.close()
    
    return rows, cols, sql
