# Day04 ReAct Supplement Advisor Design

The application is a new FastAPI and React codebase alongside the untouched
`starter_v0/`. It uses a free-form LangGraph ReAct loop whose tools are deterministic,
grounded in `shared_data/DataTPCN.csv`, and protected by a final safety validator.

Stable infrastructure belongs to `backend/app/agent/shared/`. Version-specific prompts,
tool allowlists, limits, and graph assembly belong to
`backend/app/agent/version_1/`. Future versions import shared code but never another
version.

SQLite stores sessions with incremental context, messages, runs, and structured trace events.
LangGraph checkpoints use a separate SQLite file. Chroma stores local product vectors;
collection identity includes the dataset and embedding-model fingerprints.

The mentor UI has chat/comparison and structured trace panels. It shows
state transitions, retrieval, tool calls, scoring, safety decisions, latency, and usage,
but never raw hidden chain-of-thought.

The CSV is the sole product evidence source. The product-fit score is not a product
quality or clinical efficacy score. Explicit contraindication matches exclude a
candidate; unknown medication or condition evidence requires professional review.
