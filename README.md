# SignalHub

### Evidence-Backed Account Intelligence & RAG Signal Extraction

SignalHub is a Mastek-focused portfolio project that turns public account information into traceable, evidence-backed intelligence for research, pre-sales, and sales workflows.

The system combines bounded public-web ingestion, semantic retrieval, and LLM-grounded generation to surface relevant account developments and structured business signals while preserving source provenance.

## What SignalHub Does

SignalHub is designed around a simple pipeline:

```text
Public Account Sources
        ↓
Research Agent
        ↓
Document Ingestion
        ↓
LanceDB Semantic Retrieval
        ↓
RAG Signal Agent
        ↓
Gemini LLM
        ↓
Structured, Evidence-Backed Signals
```

The system is designed to answer:

> What is happening at this account, what signals can we extract from the evidence, and can every claim be traced back to a source?

## Current Implementation

### Research Agent

The Research Agent discovers and collects public account information from approved sources.

Implemented capabilities include:

* bounded same-domain web ingestion
* HTML and PDF document extraction
* source classification
* publication-date detection
* document deduplication and idempotent re-ingestion
* account-scoped LanceDB retrieval
* relevant-document ranking
* fallback to previously indexed evidence when external search is unavailable
* research-gap handling
* source and URL preservation

Supported source categories include company pages, press releases, investor material, annual reports, jobs, events, partner content, and news sources.

### RAG-Based Signal Agent

Retrieved account evidence is passed to an LLM only after semantic retrieval.

The Signal Agent:

* performs focused account-scoped LanceDB retrieval
* combines SentenceTransformers embeddings with vector search
* supplies retrieved evidence to Gemini as grounded context
* extracts structured technology, transformation, investment, partnership, and hiring signals
* distinguishes `OBSERVED`, `DERIVED`, and `INFERRED` claims
* assigns confidence scores
* preserves document, chunk, and source references
* validates LLM-generated evidence IDs against the actual retrieved evidence
* rejects unsupported or fabricated references
* returns partial results rather than fabricating output when the LLM is unavailable

## Evidence & Grounding

Evidence traceability is a core design principle.

LLM-generated signals reference stable evidence IDs such as:

```text
E1
E2
E3
```

These IDs are resolved back to the original document, chunk, source, and URL by the application rather than being trusted directly from the LLM.

The intended evidence chain is:

```text
Signal
  ↓
Claim
  ↓
Evidence
  ↓
Document
  ↓
Source
  ↓
URL
```

This makes generated intelligence auditable and helps prevent unsourced claims from reaching downstream workflows.

## Example Signal

For an account such as Schneider Electric, retrieved evidence can produce structured signals such as:

```text
Signal Type: TECHNOLOGY
Claim Type: OBSERVED
Title: AI-powered industrial automation initiative
Confidence: 0.91

Evidence:
- Document ID
- Chunk ID
- Source URL
```

The system does not allow the LLM to invent source IDs or URLs that were not present in the retrieved evidence.

## Technology Stack

**Backend**

* Python
* FastAPI
* SQLAlchemy
* PostgreSQL / SQLite for local development

**AI / Retrieval**

* SentenceTransformers
* LanceDB
* Gemini API
* Pydantic

**Data Processing**

* BeautifulSoup
* PyMuPDF
* Pandas

**Engineering**

* Docker
* Pytest
* GitHub Actions
* Git

**Frontend**

* React
* Vite
* Tailwind CSS

## Project Architecture

```text
backend/
├── app/
│   ├── agents/
│   │   ├── research.py
│   │   └── signals.py
│   ├── ingestion/
│   ├── retrieval/
│   ├── models/
│   ├── config.py
│   └── main.py
│
scripts/
├── init_db.py
└── signal_agent_smoke.py
│
tests/
├── test_research_agent.py
└── test_signal_agent.py
│
docs/
└── architecture.md
```

## Local Development

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd signalhub
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install the project dependencies

Use the dependency configuration included in the repository.

For an editable package installation, when supported by the repository:

```powershell
pip install -e .
```

### 4. Configure environment variables

Copy the example configuration:

```powershell
Copy-Item .env.example .env
```

For Gemini-based RAG signal extraction, configure:

```env
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-2.5-flash-lite
```

Keep `.env` local. Do not commit API keys.

### 5. Initialize the database

For the quickest local setup, use the default SQLite configuration.

```powershell
python scripts/init_db.py
```

For PostgreSQL development, start the database with:

```powershell
docker compose up -d
```

and configure the PostgreSQL `DATABASE_URL` in `.env`.

### 6. Start the API

From the repository root:

```powershell
uvicorn app.main:app --reload
```

## Running Tests

Run the complete test suite:

```powershell
python -m pytest -q
```

The current test suite covers:

* Research Agent discovery and failure handling
* account-scoped retrieval
* fallback evidence retrieval
* source classification
* generic-page ranking
* RAG signal extraction
* evidence grounding
* invalid evidence references
* LLM failure handling
* inferred signals
* persistence and evidence relationships

The current suite contains **23 automated tests**.

## Manual RAG Smoke Test

SignalHub includes a manual smoke test that uses the real indexed account evidence and configured Gemini API.

```powershell
$env:PYTHONPATH = "backend"
python scripts/signal_agent_smoke.py
```

The smoke test retrieves real account evidence from LanceDB and sends only the retrieved evidence to Gemini. It prints the generated signals together with their claim types, confidence, and source references.

It does not depend on GDELT for the RAG generation test.

## Design Principles

### Evidence First

Generated intelligence should be traceable to an underlying source.

### Retrieval Before Generation

The LLM does not independently browse the web for signal generation. Relevant account evidence is retrieved first and provided as grounded context.

### Explicit Inference

The system distinguishes observed facts from derived and inferred conclusions.

### Graceful Failure

External search and LLM failures produce explicit research gaps and partial results rather than fabricated intelligence.

### Provider-Agnostic Architecture

The AI components are designed around injectable interfaces so the retrieval and reasoning layers can evolve independently of a specific model provider.

## Roadmap

The current implementation focuses on the research and RAG signal-extraction foundation.

Planned extensions include:

* account prioritisation and ICP scoring
* opportunity and whitespace analysis
* Mastek capability matching
* detailed pre-sales account briefs
* plain-English sales briefs
* competitor and partner intelligence
* event intelligence and account mapping
* HubSpot engagement context
* research requests and internal workflow management
* human review and approval
* change detection and scheduled refreshes
* alerts and weekly intelligence digests
* content and SEO analytics integrations
* marketing MQL/SQL intelligence

These features are part of the planned platform roadmap and are not represented as completed functionality in the current release.

## Portfolio Context

SignalHub was built as a focused portfolio project around the intersection of:

* account intelligence
* information retrieval
* RAG
* LLM applications
* evidence-grounded generation
* sales and pre-sales intelligence

The project emphasizes not only generating useful outputs, but also making those outputs **traceable, verifiable, and auditable**.
