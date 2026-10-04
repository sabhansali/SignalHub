# SignalHub — Windows runbook

## 1. Create the environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

## 2. Cheapest local mode

The application defaults to SQLite when `DATABASE_URL` is not set. This lets you work on the API/data model without running PostgreSQL.

```powershell
python scripts/init_db.py
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health`.

## 3. PostgreSQL mode

Install Docker Desktop separately, then:

```powershell
docker compose up -d
python scripts/init_db.py
```

Set `DATABASE_URL` in `.env` to:

```text
postgresql+psycopg://signalhub:signalhub@localhost:5432/signalhub
```

## 4. First account seed

The initial seed is Schneider Electric (Manufacturing / India), using public official company, newsroom, investor, annual-report, and careers pages.

```powershell
python scripts/seed_account.py
```

The seed script can index chunks into LanceDB when the LanceDB and embedding dependencies are installed.

## 5. Development checks

```powershell
pytest -q
python -m compileall backend scripts
```
