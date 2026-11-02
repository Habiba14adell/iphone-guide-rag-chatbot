# iPhone Guide Assistant

A chatbot for the supplied iPhone User Guide, using LangGraph, Chainlit,
Qdrant Cloud, and Gemini. Answers use retrieved guide passages and show PDF
page references. The assistant is instructed to decline questions that the
retrieved passages cannot answer.

## Run with Docker

Use Docker with Linux containers. Clone the repository and create `.env`:

```powershell
git clone https://github.com/Habiba14adell/iphone-guide-rag-chatbot.git
cd iphone-guide-rag-chatbot
Copy-Item .env.example .env
```

Fill in the connection details and API keys:

```dotenv
QDRANT_URL="https://your-qdrant-cluster-url"
QDRANT_API_KEY="your-qdrant-key"
QDRANT_COLLECTION="iphone_user_guide"
RETRIEVAL_TOP_K=5
GEMINI_API_KEY="your-gemini-key"
GEMINI_MODEL="gemini-3.5-flash-lite"
```

| Variable | Purpose |
| --- | --- |
| `QDRANT_URL` | URL of the cluster containing the guide |
| `QDRANT_API_KEY` | Key with read access to the existing collection |
| `QDRANT_COLLECTION` | Collection name; default `iphone_user_guide` |
| `RETRIEVAL_TOP_K` | Number of retrieved chunks; default 5 |
| `GEMINI_API_KEY` | API key for answer generation |
| `GEMINI_MODEL` | Gemini model ID available to the API key |

The evaluator needs access to the populated Qdrant collection. Share its URL
and an appropriate query key privately. A key from another cluster will not
work. Keep credentials out of Git and the source ZIP.

```powershell
docker build -t chatbot:1.0 .
docker run -p 8000:8000 --env-file .env chatbot:1.0
```

Open **http://localhost:8000**.

The first build downloads dependencies and the embedding model. Query
embeddings run on the CPU using the model cached in the image. Internet access
is required to reach Qdrant Cloud and Gemini. Chat startup uses the existing
collection; it does not process the PDF, upload vectors, or create a collection.
The local PDF and ingestion artifacts are not required to start chatting.

Stop the container with Ctrl+C. Rebuild after code changes. Docker build and
container startup have not yet been verified on the development machine.

## Run locally without Docker

Use Python 3.12 and configure `.env` as above. In PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m chainlit run src/iphone_guide_chatbot/ui/app.py --port 8000
```

Open http://localhost:8000. The model downloads when first needed if it is not
cached. Restart Chainlit after changing code or `.env`. If an inherited `DEBUG`
value causes a configuration error, set `$env:DEBUG='false'` before starting.

## How it works

```text
User question ? Retrieve passages ? Generate answer ? Display answer and sources
```

Chainlit passes each question to the LangGraph workflow. Retrieval generates a
BGE query embedding and searches Qdrant using cosine similarity. Results retain
content, similarity scores, and metadata. PDF and printed pages are derived
from `source_spans`.

Gemini receives the question, conversation history, and retrieved excerpts.
The prompt requires source markers for factual claims. The application checks
that cited IDs belong to retrieved chunks and adds page references from stored
metadata. Only cited chunks appear in the source list and source panels.
Answers with missing or unknown source IDs are withheld. The standard
insufficient-information response displays no sources.

Session history stores questions and answer text without source lists, panels,
or inline citation markers. History provides conversational context, while
factual evidence must come from the current excerpts. It is not persisted
across restarts. Retrieval currently searches only the latest question, so
ambiguous follow-ups may retrieve unsuitable passages. There is no separate
relevance judge or question-rewriting node.

## Models

- Embeddings: `BAAI/bge-small-en-v1.5`, 384-dimensional normalized vectors,
  cosine similarity. Ingestion and retrieval reuse the embedding implementation.
- Answers: Gemini through `google-genai`, default `gemini-3.5-flash-lite`.
  Change `GEMINI_MODEL` to select another available model.

The earlier ingestion report recorded tokenizer revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. The default model setting resolves
`main`; each ingestion run saves its resolved revision in the run summary.
Gemini model IDs follow the provider's versioning.

## Local PDF ingestion

Ingestion runs separately from chat and does not connect to Qdrant. Place the
source at `Data/iPhone User Guide 1.pdf`, or change `PDF_PATH` in
`src/iphone_guide_chatbot/config/settings.py`.

Configure the run in that settings file:

| Setting | Default |
| --- | --- |
| `OUTPUT_PATH` | `artifacts/ingestion` |
| `MODEL_NAME` | `BAAI/bge-small-en-v1.5` |
| `MODEL_REVISION` | `main` |
| `TARGET_TOKENS` | 350 |
| `MAX_TOKENS` | 450 |
| `OVERLAP_TOKENS` | 50 |
| `MODEL_LIMIT` | 512 |
| `BATCH_SIZE` | 32 |
| `SKIP_EMBEDDINGS` | `False` |

Set `SKIP_EMBEDDINGS = True` to review chunks without generating document
vectors. Run the same command for either mode:

```powershell
.venv\Scripts\python.exe scripts\ingest_pdf.py
```

Ingestion reads settings directly and does not accept command-line options.

Extraction uses layout and contents entries to identify chapters and sections.
It retains PDF and printed page numbers, reconstructs table rows where possible,
and marks detected inline controls as `[icon in PDF]` without guessing their
meaning. Section-aware recursive chunking keeps procedures, table rows, and
notices together where possible. Token counts include headings and special
tokens. Overlap stays within the section and may be shortened or dropped to
respect the hard limit.

Chunks preserve IDs, chapter and section names, page ranges, content types,
text, token counts, and detailed `source_spans`. Unchanged chunks can retain
their previous IDs. Notices can carry links to related context chunks.

Outputs are saved under `OUTPUT_PATH`:

| File | Contents |
| --- | --- |
| `pages.jsonl` | Raw text, page references, extraction flags, and corrections |
| `chunks.jsonl` | Chunk text and metadata |
| `ingestion_summary.json` | Counts, configuration, source hash, headings, resolved revision, and embedding status |
| `embeddings.npy` | Normalized vectors, full run only |
| `embedding_ids.jsonl` | Mapping between vector rows and chunk IDs, full run only |

The separate validation stage has been removed. Chunking and embedding still
check their token limits. Vector saving checks counts, finite values, and
normalization. Old validation and inspection reports are not regenerated.

Outputs are overwritten on rerun. Use another `OUTPUT_PATH` to compare runs.
Skipping embeddings does not remove older vector files, so consult the current
summary's `embeddings_generated` value before using them.

The upload and collection-creation scripts are separate manual operations.
They never run at chat startup. The uploader generates embeddings from the
chunk file and writes points to Qdrant; it is not needed to run the chatbot
against the populated collection.

## Project structure

Local data, generated artifacts, logs, tests, documentation, and caches are
excluded from this tree.

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
|       |-- __init__.py
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
|       |   `-- pipeline.py
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
|       `-- ui/
|           |-- __init__.py
|           `-- app.py
|-- .dockerignore
|-- .env.example
|-- .gitignore
|-- chainlit.md
|-- Dockerfile
|-- README.md
`-- requirements.txt
```

## Logging and checks

Application logs append to `logs/YYYY-MM-DD.log` using Cairo time. Docker logs
remain inside the container unless a host directory is mounted. Secrets,
local data, and generated files are excluded from the build context.

The last full test attempt was blocked by an ingestion test importing the
validation module that was moved out of the application. Existing tests were
left unchanged. With that ingestion test excluded, 13 tests passed. Both
ingestion modes also passed mocked pipeline checks. Docker and live
answer-and-citation testing remain to be completed.

Citation checks verify source IDs and page mapping, not whether every claim
is supported in meaning. Extraction uses layout rules rather than OCR or image
understanding. Review complex diagrams and cited passages against the PDF.
