# AI RAG Platform

Enterprise-grade RAG platform for housing cooperatives (borettslag) and SMBs.

This platform enables organizations to upload internal documents and allow users to retrieve accurate answers through AI-powered semantic search and conversational retrieval.

---

# Core Features

* PDF upload and ingestion
* OpenAI embeddings (`text-embedding-3-small`)
* FAISS vector search
* Hybrid retrieval (Vector + BM25)
* Query rewriting
* Chunk deduplication
* Persistent vector storage
* Source citations
* FastAPI backend
* Production-ready architecture foundation

---

# Use Cases

## Housing Cooperatives (Borettslag)

Residents can ask questions like:

* "Who do I contact regarding parking?"
* "When is the planned rehabilitation?"
* "What are the house rules for noise?"
* "What internet agreement does the board have?"

The AI retrieves answers directly from uploaded board documents, agreements, and regulations.

---

## SMB / Business

Potential customers can ask:

* "What services do you offer?"
* "What does implementation cost?"
* "Do you support integrations?"
* "Can I get an estimate?"

The system can later be extended with:

* lead generation
* quotation generation
* CRM integrations
* sales automation

---

# Tech Stack

## Backend

* FastAPI
* OpenAI API
* FAISS
* BM25
* NumPy
* PyPDF2

## Infrastructure

* Render
* Vercel
* Supabase (planned multi-tenant architecture)

---

# Project Structure

```bash
backend/
 ├── app/
 │    └── main.py
 │
 ├── requirements.txt
 ├── .env
 └── .env.example

frontend/
 └── src/
```

---

# Local Development

## 1. Create virtual environment

```bash
cd backend
python -m venv venv
```

## 2. Activate environment

### Windows

```bash
venv\Scripts\activate
```

### Mac/Linux

```bash
source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Create .env

```env
OPENAI_API_KEY=your_key_here
```

## 5. Run backend

```bash
uvicorn app.main:app --reload
```

Backend runs on:

```text
http://127.0.0.1:8000
```

Swagger docs:

```text
http://127.0.0.1:8000/docs
```

---

# Roadmap

## v2

* Multi-tenant architecture
* Supabase authentication
* Organization roles & permissions
* Citation grounding
* Better reranking

## v3

* CRM integrations
* Analytics dashboard
* Conversation memory
* Admin portal
* Usage billing

---

# Status

Early production architecture in active development.
