import os
import re
import sqlite3
from typing import Any, List, Optional, Tuple
from dotenv import load_dotenv

# LangChain imports
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "amazon.db")
DB_URL = f"sqlite:///{DB_PATH.replace(os.sep, '/')}"

# Strict Security Constraints
FORBIDDEN_KEYWORDS = (
    "DROP", "DELETE", "UPDATE", "INSERT",
    "ALTER", "TRUNCATE", "CREATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM"
)

# Prioritized ranking of models best suited for Text-to-SQL tasks
PREFERRED_SQL_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "deepseek-r1-distill-llama-70b",
    "qwen-2.5-32b",
    "gemma2-9b-it",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-3b-preview",
    "llama-3.2-1b-preview",
]

SQL_PROMPT_TEMPLATE = """You are an expert SQLite SQL generator.
Given the database schema and a user question, write a valid SQLite query.

Database Schema:
{schema}

Strict Rules:
1. Return ONLY the raw SQL query. No markdown formatting, no backticks, no explanations.
2. Read-only: Only SELECT or WITH statements are allowed. Never write modifying statements.
3. Minimum Joins: Query ONLY the specific table(s) necessary to answer the question.
   - Do NOT join orders, order_items, or products unless the user explicitly asks about them.
   - For queries about customers (e.g. 'customers from New York'), query ONLY the `customers` table!
   - Use `SELECT DISTINCT` if joins could produce duplicate parent records.
4. Dialect: Use SQLite functions only.
   - For dates: use strftime('%Y-%m-%d', ...) or date(...)
   - For string concatenation: use ||
   - For case-insensitive comparison: use LIKE or LOWER(...)
5. Semicolons: Do NOT chain multiple queries. Write exactly one single statement.
6. Limit: If no specific row limit is requested, append LIMIT 100.
7. Use only existing tables and columns from the schema above.

Question: {question}
SQL:"""

CORRECTION_PROMPT_TEMPLATE = """You previously generated a SQLite query that failed with an error:
Failed Query: {failed_sql}
Error Message: {error_msg}

Database Schema:
{schema}

Please rewrite the query to fix the error. Query ONLY the minimum necessary tables.
Return ONLY the raw SQL query. No explanations, no markdown.
Corrected SQL:"""


def validate_question_safety(question: str) -> Optional[str]:
    """Check if the user question is requesting a destructive operation."""
    q_lower = question.lower().strip()
    destructive_patterns = [
        r"\bdelete\b", r"\bdrop\b", r"\btruncate\b",
        r"\bupdate\b.*\bset\b", r"\binsert\b.*\binto\b",
        r"\balter\s+table\b", r"\bremove\s+all\b"
    ]
    for pattern in destructive_patterns:
        if re.search(pattern, q_lower):
            return "Security Violation: Destructive operations (DELETE, DROP, UPDATE, INSERT, ALTER) are strictly prohibited. QueryAI is read-only."
    return None



def get_langchain_db() -> Optional[SQLDatabase]:
    """Initialize LangChain SQLDatabase with sample rows and SQLite dialect introspection."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        return SQLDatabase.from_uri(
            DB_URL,
            include_tables=["customers", "products", "orders", "order_items"],
            sample_rows_in_table_info=2
        )
    except Exception:
        return None


def get_schema() -> str:
    """Get rich schema information with sample rows via LangChain SQLDatabase."""
    db = get_langchain_db()
    if db is None:
        return "{}"
    return db.get_table_info()


def clean_sql(raw_sql: str) -> str:
    """Extract and sanitize SQL from LLM response."""
    match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", raw_sql, re.IGNORECASE)
    sql = match.group(1).strip() if match else raw_sql.strip()
    sql = sql.strip("`").strip()
    return sql.rstrip(";").strip()


def validate_sql_safety(sql: str) -> Optional[str]:
    """Validate that the query conforms strictly to read-only security constraints.
    Returns None if valid, or an error string if violated."""
    clean = sql.strip()
    clean_no_semi = re.sub(r";\s*$", "", clean)

    # Rule 1: No multiple statements / chained semicolons
    if ";" in clean_no_semi:
        return "Security Violation: Multiple SQL statements or chained semicolons are prohibited."

    # Rule 2: Must begin with SELECT, WITH, or EXPLAIN
    upper = clean_no_semi.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH") or upper.startswith("EXPLAIN")):
        return f"Security Violation: Only read-only SELECT queries are allowed. Attempted:\n{sql}"

    # Rule 3: Word-boundary check for forbidden mutating keywords
    tokens = set(re.findall(r"\b[A-Z_]+\b", upper))
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in tokens:
            return f"Security Violation: Forbidden keyword '{keyword}' detected. Only read-only queries are allowed."

    return None


def get_llm_instance(model_name: str, api_key: str):
    """Instantiate a LangChain chat model with Groq."""
    try:
        from langchain_groq import ChatGroq
        return ChatGroq(model=model_name, api_key=api_key, temperature=0)
    except ImportError:
        from groq import Groq
        class DirectGroqWrapper:
            def __init__(self, model: str, key: str):
                self.model = model
                self.client = Groq(api_key=key)

            def invoke(self, prompt_text: str) -> str:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": str(prompt_text)}],
                    temperature=0
                )
                return resp.choices[0].message.content or ""
        return DirectGroqWrapper(model_name, api_key)


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
        from groq import Groq
        client = Groq(api_key=api_key)
        res = client.models.list()
        chat_models = [
            m.id for m in res.data
            if not any(k in m.id.lower() for k in ["whisper", "guard", "embed", "tts", "transcription"])
        ]
        return chat_models
    except Exception:
        return []


def execute_sql_safely(sql: str) -> Tuple[Optional[List[Tuple[Any, ...]]], List[str], str]:
    """Execute SQL using engine-level read-only mode and row limiting.
    Returns (rows, cols, executed_sql). Raises Exception on execution failure."""
    clean_query = sql.strip().rstrip(";")
    if "LIMIT" not in clean_query.upper():
        clean_query = f"{clean_query} LIMIT 100"

    # Enforce SQLite engine-level read-only mode via URI
    db_uri = f"file:{DB_PATH.replace(os.sep, '/')}?mode=ro"
    try:
        conn = sqlite3.connect(db_uri, uri=True, timeout=10.0)
    except Exception:
        # Fallback to standard path if URI mode is unsupported on environment
        conn = sqlite3.connect(DB_PATH, timeout=10.0)

    try:
        cur = conn.cursor()
        cur.execute(clean_query)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description] if cur.description else []
        return rows, cols, clean_query
    finally:
        conn.close()


def make_sql(schema: str, question: str) -> Tuple[str, str, Optional[Any]]:
    """Turn a question into SQL using LangChain with automatic top-to-bottom model failover."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass

    if not api_key:
        return "Error: GROQ_API_KEY not set. Please set it in your .env file, Streamlit secrets, or sidebar.", "", None

    live_models = get_available_models(api_key=api_key)
    candidate_models: List[str] = []
    custom_model = os.getenv("GROQ_MODEL")
    if custom_model:
        candidate_models.append(custom_model)

    for m in PREFERRED_SQL_MODELS:
        if m not in candidate_models:
            if not live_models or m in live_models:
                candidate_models.append(m)

    # Append remaining live models, placing non-coding/regional models like allam at the end
    other_models = [m for m in live_models if m not in candidate_models]
    sorted_others = sorted(other_models, key=lambda x: (1 if "allam" in x.lower() else 0, x))
    candidate_models.extend(sorted_others)

    if not candidate_models:
        candidate_models = list(PREFERRED_SQL_MODELS)

    prompt = ChatPromptTemplate.from_template(SQL_PROMPT_TEMPLATE)

    attempt_errors = []
    for model_name in candidate_models:
        try:
            llm = get_llm_instance(model_name, api_key)
            if hasattr(llm, "invoke"):
                formatted_prompt = prompt.format(schema=schema, question=question)
                response_text = llm.invoke(formatted_prompt)
                raw_sql = getattr(response_text, "content", response_text)
            else:
                raise Exception("LLM instance failed to initialize.")

            sql = clean_sql(str(raw_sql))
            safety_violation = validate_sql_safety(sql)
            if safety_violation:
                return f"Error: {safety_violation}", model_name, None

            return sql, model_name, llm

        except Exception as err:
            attempt_errors.append(f"{model_name}: {err}")
            continue

    error_summary = " | ".join(attempt_errors)
    return f"Error: All models in the auto-failover chain failed: {error_summary}", "", None


def query(question: str) -> Tuple[Optional[List[Tuple[Any, ...]]], List[str], str, str]:
    """Run a natural language query with LangChain, strict validation, and self-correction."""
    if not os.path.exists(DB_PATH):
        return None, [], f"Error: Database file '{DB_PATH}' does not exist. Please run create_database.py first.", ""

    # Strict Security: Intercept destructive intentions in user prompt
    safety_violation = validate_question_safety(question)
    if safety_violation:
        return None, [], f"Error: {safety_violation}", ""

    schema = get_schema()
    sql, model_used, llm = make_sql(schema, question)

    if sql.lower().startswith("error"):
        return None, [], sql, model_used

    # Attempt execution with automatic self-correction loop
    try:
        rows, cols, executed_sql = execute_sql_safely(sql)
        return rows, cols, executed_sql, model_used
    except Exception as first_err:
        # LangChain Self-Correction Loop: Attempt query rewrite
        if llm:
            try:
                correction_prompt = ChatPromptTemplate.from_template(CORRECTION_PROMPT_TEMPLATE)
                formatted_corr = correction_prompt.format(
                    failed_sql=sql,
                    error_msg=str(first_err),
                    schema=schema
                )
                corr_resp = llm.invoke(formatted_corr)
                raw_corr = getattr(corr_resp, "content", corr_resp)
                fixed_sql = clean_sql(str(raw_corr))

                safety_violation = validate_sql_safety(fixed_sql)
                if not safety_violation:
                    rows, cols, executed_sql = execute_sql_safely(fixed_sql)
                    return rows, cols, f"{executed_sql} -- (Self-corrected after: {first_err})", model_used
            except Exception:
                pass

        return None, [], f"Error executing query: {first_err}\n\nSQL attempted:\n{sql}", model_used




