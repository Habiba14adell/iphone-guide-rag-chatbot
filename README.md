# iPhone Guide RAG Chatbot

A document-grounded conversational assistant for the supplied iPhone User Guide.
This repository is being built incrementally for the Generative AI technical assessment.

## Project structure

```text
iphone-guide-rag-chatbot/
|-- artifacts/ingestion/          # Local generated chunks, vectors, and reports
|-- Data/                        # Existing source PDF (filename unchanged)
|-- docs/
|   |-- ingestion.md
|   |-- ingestion-review.md
|   `-- rag-workflow.md
|-- logs/                        # Daily application logs
|-- scripts/
|   |-- ingest_pdf.py
|   |-- upload_to_qdrant.py
|   `-- create_qdrant_collection.py
|-- src/iphone_guide_chatbot/
|   |-- __init__.py
|   |-- config/
|   |   |-- __init__.py
|   |   |-- settings.py
|   |   `-- logging_config.py
|   |-- ingestion/
|   |   |-- __init__.py
|   |   |-- extraction.py
|   |   |-- layout.py
|   |   |-- chunking.py
|   |   |-- embeddings.py
|   |   |-- validation.py
|   |   `-- pipeline.py
|   |-- retrieval/
|   |   |-- __init__.py
|   |   `-- retriever.py          # Read-only semantic retrieval
|   |-- rag/
|   |   |-- __init__.py
|   |   |-- graph.py              # Retrieval and relevance routing
|   |   |-- nodes.py              # Retrieval and evaluator interface
|   |   |-- state.py              # Shared AgentState
|   |   `-- prompts.py            # Empty placeholder
|   `-- ui/
|       |-- __init__.py
|       |-- app.py                # Chainlit session handlers
|       `-- presentation.py       # Source display formatting
|-- tests/                       # Existing files remain in place
|   |-- .gitkeep
|   |-- conftest.py
|   |-- test_ingestion.py
|   |-- test_retrieval.py
|   |-- qdrant.py
|   `-- QDEANT_.PY
|-- checks/                      # Additional offline backend/UI checks
|-- .chainlit/config.toml         # Chainlit name, theme, and features
|-- chainlit.md                   # UI information page
|-- .env                         # Local credentials; ignored by Git
|-- .env.example
|-- .gitignore
|-- requirements.txt
|-- requirements-dev.txt
`-- README.md
```

Ingestion configuration lives in `src/iphone_guide_chatbot/config/settings.py`.
The extraction, chunking, and validation behavior is unchanged. Retrieval and the
initial LangGraph workflow are implemented. Chainlit displays source excerpts for
inspection; relevance evaluation and answer generation are not configured.

The standalone cloud scripts have moved to `scripts/`. From the repository root,
their entry points are:

```powershell
.venv\Scripts\python.exe scripts\upload_to_qdrant.py
.venv\Scripts\python.exe scripts\create_qdrant_collection.py
```

These are explicit operational commands, not part of application startup. The
uploader retains its existing behavior of generating embeddings from the chunks
before uploading. Restructuring does not execute either cloud script. Manual
retrieval and connection checks remain in their original locations under `tests/`.

## Required application behaviour

- Answer strictly from the supplied PDF and explicitly decline when it lacks an answer.
- Cite the source page and/or section for document-based answers.
- Support multi-turn conversations within a session.
- Use LangChain and/or LangGraph, a cloud-hosted vector database, and Chainlit or Streamlit.
- Run locally in a single Docker container against an already populated cloud index.

## Run the conversational UI

The interface is named **iPhone Guide Assistant**. Install the updated dependencies
in the project environment, then run from the repository root:

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
$env:DEBUG='false'
.venv\Scripts\python.exe -m chainlit run src/iphone_guide_chatbot/ui/app.py --headless --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000**. The `DEBUG` setting prevents an inherited nonboolean
value from interfering with Chainlit's command-line configuration. The existing
`.env` supplies Qdrant credentials; do not enter API keys in the chat.

Ask a question such as ?How can I connect my iPhone to a Wi-Fi network?? A loading
indicator covers the graph invocation. Each response is explicitly labeled
**retrieved context, not a final answer**. The source links open the complete
excerpts, section/chapter names, PDF pages, and printed page references. Markers
such as `[icon in PDF]` require inspecting the cited PDF page.

Conversation history and the compiled graph are held in each Chainlit session.
A new chat has a separate history; no database persistence is configured. History
is passed to the workflow for future use, but follow-up question rewriting is not
implemented. The UI does not create a relevance evaluator or generate answers.

Starting the UI does not extract the PDF, generate document embeddings, create
collections, or upload points. Only questions generate query embeddings and
read the existing collection. The first model load can take longer than later
searches. With the model cached, `$env:HF_HUB_OFFLINE='1'` avoids model downloads.

Run all existing and additional offline checks without changing `tests/`:

```powershell
.venv\Scripts\python.exe -m pytest -q tests checks
```

Browser validation uses Playwright with the installed Microsoft Edge browser.
Screenshots from validation are local files under `artifacts/ui/`, excluded from Git.

## Local PDF ingestion

The chosen stack is LangGraph, Chainlit, and Qdrant Cloud. The current ingestion
pipeline runs locally and does not connect to Qdrant.

Use Python 3.12 and install `requirements.txt` into a virtual environment. From
the repository root, run:

```powershell
.venv\Scripts\python.exe scripts\ingest_pdf.py
```

The default PDF is `Data/iPhone User Guide 1.pdf`. The source PDF is local and
excluded from Git. Use `--pdf` to supply a different path. The first run downloads
the public BGE model and tokenizer into `.cache/huggingface`; no API key is needed.
To review chunks without computing embeddings:

```powershell
.venv\Scripts\python.exe scripts\ingest_pdf.py --skip-embeddings
```

Outputs in `artifacts/ingestion/`:

- `pages.jsonl`: raw extracted text, PDF/printed page numbers, and quality flags.
- `chunks.jsonl`: chunk text, required metadata, token counts, and source spans.
- `inspection.txt`: counts for every chunk, extraction warnings, and ten samples.
- `validation.json`: budget/reference checks, detected headings, source hash,
  resolved model revision, and embedding status.
- `embeddings.npy`: normalized vectors, one row per chunk (full run only).
- `embedding_ids.jsonl`: explicit mapping from vector rows to chunk IDs.

The BGE tokenizer counts the exact text embedded, including chapter/section
titles and special tokens. Defaults are a 350-token target, 450-token maximum,
and up to 50 tokens of overlap within a section. Protected blocks can exceed the
soft target to stay intact; no chunk may exceed the hard maximum or the model
limit. Overlap is shortened or omitted to avoid fragmenting protected blocks or
exceeding the budget. `--model`, `--revision`, `--target-tokens`, `--max-tokens`,
`--overlap-tokens`, `--model-limit`, and `--batch-size` configure the pipeline.
Both tokenizer and embedder use the resolved model revision. See
[ingestion design notes](docs/ingestion.md) for extraction rules and limitations.

Install `requirements-dev.txt` to run checks:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

After the model is cached, set `$env:HF_HUB_OFFLINE='1'` for an offline run.
Artifacts, downloaded models, the virtual environment, and logs are ignored by Git.

## Logging

Install `requirements.txt` for timezone support on Windows. Call `setup_logging()`
from `iphone_guide_chatbot.config.logging_config` at each entry point's startup,
then use `logging.getLogger(__name__)` in each module.

Events at INFO level and above append to `logs/YYYY-MM-DD.log`, using Cairo time.
The first entry after midnight switches to the new day's file. Repeated setup
calls do not add duplicate daily handlers; existing console handlers are preserved.
Use `logger.exception("Description of the failure")` inside an exception handler
to include its traceback. Never log API keys, credentials, or full request headers.
Logs are ignored by Git. Mount the logs directory in Docker to retain files after
container removal. Application entry points will be wired up as they are built.

