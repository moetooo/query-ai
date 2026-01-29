# QueryAI

Text-to-SQL tool. Type a question, get database results.

## Local Setup

```bash
# Install
pip install -r requirements.txt

# Set API key
# Windows: $env:GROQ_API_KEY="your-key"
# Or create .env file with: GROQ_API_KEY=your-key

# Run
streamlit run frontend.py
```

## Deploy to Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo
4. Set main file: `frontend.py`
5. Add secret in Settings > Secrets:
   ```
   GROQ_API_KEY = "your-groq-api-key"
   ```
6. Deploy

## Get Groq API Key

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (free)
3. Create API key
4. Copy and add to secrets

## Files

- `frontend.py` - UI
- `main.py` - text-to-sql logic
- `amazon.db` - database
- `requirements.txt` - dependencies
