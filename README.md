# iPhone Guide RAG Chatbot

A document-grounded conversational assistant for the supplied iPhone User Guide.
This repository is being built incrementally for the Generative AI technical assessment.

## Project structure

```text
iphone-guide-rag-chatbot/
├── Data/                       # Supplied source PDF
├── docs/                       # Architecture and design decisions
├── scripts/                    # Ingestion and maintenance entry points
├── src/
│   └── iphone_guide_chatbot/
│       ├── config/             # Settings and environment configuration
│       ├── ingestion/          # PDF loading, chunking, and indexing
│       ├── retrieval/          # Cloud vector store access and retrieval
│       ├── rag/                # LangGraph workflow, state, and grounding
│       └── ui/                 # Conversational interface
├── tests/                      # Automated checks
├── .env.example                # Configuration template
└── .gitignore
```

## Required application behaviour

- Answer strictly from the supplied PDF and explicitly decline when it lacks an answer.
- Cite the source page and/or section for document-based answers.
- Support multi-turn conversations within a session.
- Use LangGraph for orchestration, a cloud-hosted vector database, and Chainlit or Streamlit.
- Run locally in a single Docker container against an already populated cloud index.

## Development status

LangGraph is the chosen orchestration framework. Its conversation state, nodes,
and graph definition will live in `src/iphone_guide_chatbot/rag/`.

Initial folder structure only; the application is not runnable yet. Model and
provider choices, dependencies, ingestion, UI, Dockerfile, and run instructions
will be added in subsequent steps. The final README will document the application
port, model versions, configuration, and exact Docker commands.

Keep local credentials in `.env`; never commit secrets. Required environment
variables will be documented in `.env.example` as integrations are implemented.
