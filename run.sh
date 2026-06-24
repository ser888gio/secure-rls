#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "=== secure-rls startup ==="

# 1. Install dependencies if needed
if ! python -c "import streamlit" 2>/dev/null; then
  echo "Installing dependencies..."
  pip install -r requirements.txt
fi

# 2. Generate dataset if missing
if [ ! -f "data/employees.csv" ]; then
  echo "Generating dataset..."
  python src/data/gen_data.py
fi

# 3. Initialise DB if missing
if [ ! -f "data/employees.db" ]; then
  echo "Initialising database..."
  python -c "from src.data.db import init_db; init_db()"
fi

# 4. Check Ollama is reachable
if ! curl -sf http://localhost:11434 > /dev/null 2>&1; then
  echo "ERROR: Ollama is not running. Start it with: ollama serve"
  exit 1
fi

echo "Starting app at http://localhost:8501"
echo "Credentials: acme_admin/acme123  beta_admin/beta123  gamma_admin/gamma123"
echo ""
python -m streamlit run src/ui/app.py
