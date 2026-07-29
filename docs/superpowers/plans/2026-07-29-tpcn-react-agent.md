# Day04 ReAct Supplement Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.

**Goal:** Build the approved local FastAPI, React, LangGraph, SQLite, and Chroma
version-1 supplement advisor without modifying `starter_v0/`.

**Architecture:** Shared typed domain and infrastructure back a versioned free-form
ReAct graph. Deterministic tools own retrieval, scoring, safety, comparison, and final
grounding; FastAPI persists and streams structured run events to a React mentor UI.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLAlchemy, LangGraph, Chroma,
OpenAI/Gemini adapters, React, TypeScript, Vite, Vitest, Playwright.

---

1. Build catalog parsing and typed domain models with test-first stable IDs,
   provenance, price, nutrients, package, and dosage parsing.
2. Build deterministic lexical/vector retrieval, safety, fit scoring, comparison, and
   terminal-output validation with unit tests.
3. Build SQLite repositories, trace store, provider factory, version manifest, and
   LangGraph loop with scripted-model integration tests.
4. Expose profiles, sessions, runs, resume, versions, health, and replayable SSE APIs.
5. Build the three-panel React mentor dashboard and frontend tests.
6. Add ten version-1 eval cases, local setup documentation, and complete verification.
