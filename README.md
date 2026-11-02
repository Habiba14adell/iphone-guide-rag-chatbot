# iPhone Guide RAG Chatbot

A document-grounded conversational assistant for the supplied iPhone User Guide.
This repository is being built incrementally for the Generative AI technical assessment.

## Project structure

```text
iphone-guide-rag-chatbot/
|-- .chainlit/
|   `-- config.toml
|-- scripts/
|   |-- create_qdrant_collection.py
|   |-- ingest_pdf.py
|   `-- upload_to_qdrant.py
|-- src/
|   `-- iphone_guide_chatbot/
|       |-- config/
|       |   |-- __init__.py
|       |   |-- logging_config.py
|       |   `-- settings.py
|       |-- ingestion/
|       |   |-- __init__.py
|       |   |-- chunking.py
|       |   |-- embeddings.py
|       |   |-- extraction.py
|       |   |-- layout.py
|       |   |-- pipeline.py
|       |   `-- validation.py
|       |-- llm/
|       |   |-- __init__.py
|       |   `-- gemini_client.py
|       |-- rag/
|       |   |-- __init__.py
|       |   |-- graph.py
|       |   |-- nodes.py
|       |   |-- prompts.py
|       |   `-- state.py
|       |-- retrieval/
|       |   |-- __init__.py
|       |   `-- retriever.py
|       |-- ui/
|       |   |-- __init__.py
|       |   |-- app.py
|       |   `-- presentation.py
|       `-- __init__.py
|-- .dockerignore
|-- Dockerfile
|-- .env.example
|-- .gitignore
|-- chainlit.md
|-- README.md
`-- requirements.txt
```

## Run with Docker

Install Docker Desktop and use Linux containers. Copy `.env.example` to `.env`
and fill in `QDRANT_URL`, `QDRANT_API_KEY`, and `GEMINI_API_KEY`. Keep the collection
set to `iphone_user_guide`, which already contains the guide's vectors. Change
`GEMINI_MODEL` only if you want to use another available Gemini model.

From the repository root:

```powershell
docker build -t chatbot:1.0 .
docker run -p 8000:8000 --env-file .env chatbot:1.0
```

Open [localhost:8000](http://localhost:8000). The first build downloads the Python
dependencies and BGE embedding model, so it can take a while. Later builds reuse
Docker's cached layers when possible.

The container runs Chainlit on port **8000** and uses Qdrant Cloud and Gemini.
It needs an internet connection to reach both services. The embedding model is
cached in the image and runs on the CPU. No local PDF, ingestion artifacts, or
upload command is needed to start chatting. Startup does not change the Qdrant
collection.

Credentials are supplied at runtime through `--env-file`; `.env`, local data,
logs, and generated artifacts are excluded from the Docker build context.
Logs are written inside the container to `logs/YYYY-MM-DD.log`. Stop the
container with Ctrl+C. Rebuild the image after changing the application code.

## Application flow

Chainlit passes each question to LangGraph: retrieve matching guide passages,
then generate an answer with Gemini using that context. Supported answers show
source sections and PDF page references. When the guide does not provide enough
information, the assistant declines and hides the sources. There is currently
no separate relevance judge node.

## Run without Docker

Use Python 3.12, configure `.env` as above, then run:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m chainlit run src/iphone_guide_chatbot/ui/app.py --port 8000
```

## Required application behaviour

- Answer strictly from the supplied PDF and explicitly decline when it lacks an answer.
- Cite the source page and/or section for document-based answers.
- Support multi-turn conversations within a session.
- Use LangChain and/or LangGraph, a cloud-hosted vector database, and Chainlit or Streamlit.
- Run locally in a single Docker container against an already populated cloud index.

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
Both tokenizer and embedder use the resolved model revision.

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
container removal.

