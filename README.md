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
│       ├── rag/                # Conversation orchestration and grounding
│       └── ui/                 # Conversational interface
├── tests/                      # Automated checks
├── .env                        # Configuration template
└── .gitignore
```

## Required application behaviour

- Answer strictly from the supplied PDF and explicitly decline when it lacks an answer.
- Cite the source page and/or section for document-based answers.
- Support multi-turn conversations within a session.
- Use LangChain and/or LangGraph, a cloud-hosted vector database, and Chainlit or Streamlit.
- Run locally in a single Docker container against an already populated cloud index.

