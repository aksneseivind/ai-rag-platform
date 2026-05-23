import os
import io
import re
import pickle
import numpy as np
import faiss

from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import PyPDF2
from rank_bm25 import BM25Okapi

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://ai-agent-five-plum.vercel.app",
        "https://ai-agent-lvvc.vercel.app"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# MULTI-TENANT STORAGE (ISOLATION LAYER)
# =========================================================

INDEX_PATH = "faiss.index"
CHUNKS_PATH = "chunks.pkl"
META_PATH = "meta.pkl"

DIM = 1536

index = faiss.read_index(INDEX_PATH) if os.path.exists(INDEX_PATH) else faiss.IndexFlatIP(DIM)

chunk_store = pickle.load(open(CHUNKS_PATH, "rb")) if os.path.exists(CHUNKS_PATH) else []
chunk_meta = pickle.load(open(META_PATH, "rb")) if os.path.exists(META_PATH) else []

documents = {}

# =========================================================
# BM25 HYBRID SEARCH
# =========================================================

bm25 = BM25Okapi([c.lower().split() for c in chunk_store]) if chunk_store else None

def rebuild_bm25():
    global bm25
    bm25 = BM25Okapi([c.lower().split() for c in chunk_store]) if chunk_store else None

# =========================================================
# PERSISTENCE
# =========================================================

def save_state():
    faiss.write_index(index, INDEX_PATH)

    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(chunk_store, f)

    with open(META_PATH, "wb") as f:
        pickle.dump(chunk_meta, f)

# =========================================================
# EMBEDDINGS
# =========================================================

def get_embedding(text: str):
    return client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    ).data[0].embedding

def normalize(v):
    v = np.array(v, dtype="float32")
    return v / (np.linalg.norm(v) + 1e-10)

# =========================================================
# TEXT PROCESSING
# =========================================================

def clean_text(text: str) -> str:
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()

def chunk_text(text, size=1000, overlap=150):
    text = clean_text(text)

    chunks = []
    i = 0

    while i < len(text):
        c = text[i:i+size]
        if len(c) > 80:
            chunks.append(c)
        i += size - overlap

    return chunks

def deduplicate(chunks):
    seen = set()
    out = []

    for c in chunks:
        key = c[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)

    return out

# =========================================================
# INTENT ENGINE (SMB + BORETTSLAG)
# =========================================================

def detect_intent(q: str):
    q = q.lower()

    if any(x in q for x in ["pris", "kost", "tilbud", "quote"]):
        return "smb_pricing"

    if any(x in q for x in ["styret", "vedlikehold", "borettslag", "regler"]):
        return "housing_association"

    return "general"

# =========================================================
# QUERY REWRITE
# =========================================================

def rewrite_query(q: str):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Rewrite query for semantic retrieval."
                },
                {"role": "user", "content": q}
            ],
            temperature=0
        )
        return res.choices[0].message.content
    except:
        return q

# =========================================================
# RETRIEVAL (HYBRID SCORING + RANKING)
# =========================================================

def retrieve(query, k=12):
    global bm25

    if bm25 is None:
        rebuild_bm25()

    q_emb = normalize(get_embedding(query)).astype("float32")
    q_emb = np.array([q_emb])

    scores, ids = index.search(q_emb, k)

    bm25_scores = bm25.get_scores(query.lower().split()) if bm25 else [0] * len(chunk_store)

    query_terms = set(query.lower().split())

    results = []

    for idx_pos, i in enumerate(ids[0]):
        if i == -1 or i >= len(chunk_store):
            continue

        chunk = chunk_store[i]

        vector_score = float(scores[0][idx_pos])
        bm25_score = bm25_scores[i] if i < len(bm25_scores) else 0
        overlap = len(set(chunk.lower().split()) & query_terms)
        length_bonus = min(len(chunk) / 2500, 0.12)

        score = vector_score + bm25_score * 0.5 + overlap * 0.03 + length_bonus

        results.append((score, i, chunk))

    results.sort(reverse=True, key=lambda x: x[0])

    return results

# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {"status": "enterprise-v2-live"}

# =========================================================
# UPLOAD (TENANT ISOLATION)
# =========================================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    x_tenant_id: str = Header(None)
):

    if not x_tenant_id:
        raise HTTPException(400, "Missing tenant id")

    global index, chunk_store, chunk_meta

    try:
        pdf_bytes = await file.read()
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))

        text = " ".join([(p.extract_text() or "") for p in reader.pages])

        chunks = deduplicate(chunk_text(text))

        if not chunks:
            raise HTTPException(400, "No text extracted")

        emb = client.embeddings.create(
            model="text-embedding-3-small",
            input=chunks
        )

        vectors = []

        for i, c in enumerate(chunks):
            v = normalize(emb.data[i].embedding)

            chunk_store.append(c)
            chunk_meta.append({
                "tenant_id": x_tenant_id,
                "doc": file.filename,
                "chunk_id": i
            })

            vectors.append(v)

        vectors = np.array(vectors).astype("float32")
        index.add(vectors)

        documents[file.filename] = len(chunks)

        rebuild_bm25()
        save_state()

        return {
            "status": "uploaded",
            "tenant": x_tenant_id,
            "chunks": len(chunks)
        }

    except Exception as e:
        raise HTTPException(500, str(e))

# =========================================================
# CHAT (ENTERPRISE + CITATIONS + INTENT)
# =========================================================

class ChatRequest(BaseModel):
    question: str
    tenant_id: str

class ChatResponse(BaseModel):
    answer: str
    sources: list
    intent: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    if index.ntotal == 0:
        return ChatResponse(
            answer="No documents uploaded.",
            sources=[],
            intent="none"
        )

    intent = detect_intent(req.question)
    query = rewrite_query(req.question)

    retrieved = retrieve(query, k=12)

    selected = []
    seen = set()
    sources = []

    for _, i, chunk in retrieved:

        meta = chunk_meta[i] if i < len(chunk_meta) else None

        if meta and meta.get("tenant_id") != req.tenant_id:
            continue

        key = chunk[:80]
        if key in seen:
            continue

        seen.add(key)
        selected.append(chunk)

        sources.append({
            "doc": meta["doc"] if meta else None,
            "chunk_id": meta["chunk_id"] if meta else None,
            "preview": chunk[:200]
        })

        if len(selected) == 5:
            break

    context = "\n\n".join(selected)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a RAG assistant specialized in {intent}.\n"
                    "Answer ONLY from context.\n"
                    "Always prefer citing facts from provided documents.\n\n"
                    f"CONTEXT:\n{context}"
                )
            },
            {"role": "user", "content": req.question}
        ],
        temperature=0.2
    )

    return ChatResponse(
        answer=response.choices[0].message.content,
        sources=sources,
        intent=intent
    )

# =========================================================
# DOCUMENTS
# =========================================================

@app.get("/documents")
def docs():
    return {
        "documents": list(documents.keys()),
        "chunks": len(chunk_store),
        "index_size": index.ntotal
    }