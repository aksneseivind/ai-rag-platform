import os
import io
import re
import numpy as np
import traceback

from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import PyPDF2

from supabase import create_client

# =========================================================
# INIT
# =========================================================

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase env vars")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        c = text[i:i + size]
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
# INTENT ENGINE
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
                {"role": "system", "content": "Rewrite query for semantic retrieval."},
                {"role": "user", "content": q}
            ],
            temperature=0
        )
        return res.choices[0].message.content
    except:
        return q

# =========================================================
# RETRIEVAL (SAFER + TENANT-AWARE STRATEGY)
# =========================================================

def retrieve(query_embedding, user_id, k=8):
    try:
        res = supabase.rpc(
            "match_chunks",
            {
                "query_embedding": query_embedding,
                "user_id": user_id,
                "match_count": k
            }
        ).execute()

        return res.data or []

    except Exception:
        print("RPC ERROR:\n", traceback.format_exc())
        return []

# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {"status": "supabase-rag-live"}

# =========================================================
# UPLOAD
# =========================================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Header(...)
):

    if not user_id:
        raise HTTPException(401, "Missing user_id")

    try:
        pdf_bytes = await file.read()
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))

        text = " ".join([(p.extract_text() or "") for p in reader.pages])

        chunks = deduplicate(chunk_text(text))

        if not chunks:
            raise HTTPException(400, "No text extracted")

        embeddings = client.embeddings.create(
            model="text-embedding-3-small",
            input=chunks
        )

        rows = [
            {
                "content": chunk,
                "embedding": normalize(embeddings.data[i].embedding).tolist(),
                "metadata": {
                    "chunk_index": i,
                    "filename": file.filename,
                    "user_id": user_id
                }
            }
            for i, chunk in enumerate(chunks)
        ]

        supabase.table("chunks").insert(rows).execute()

        return {
            "status": "uploaded",
            "chunks": len(rows)
        }

    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Upload failed")

# =========================================================
# CHAT
# =========================================================

class ChatRequest(BaseModel):
    question: str
    user_id: str


class ChatResponse(BaseModel):
    answer: str
    sources: list
    intent: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    if not req.user_id:
        raise HTTPException(401, "Missing user_id")

    try:
        intent = detect_intent(req.question)

        query_embedding = normalize(
            get_embedding(req.question)
        ).tolist()

        results = retrieve(
            query_embedding=query_embedding,
            user_id=req.user_id,
            k=8
        )

        if not results:
            return ChatResponse(
                answer="No relevant context found.",
                sources=[],
                intent=intent
            )

        context_chunks = []
        sources = []

        for r in results[:5]:
            content = r.get("content")
            if not content:
                continue

            context_chunks.append(content)

            sources.append({
                "chunk_id": r.get("id"),
                "preview": content[:200],
                "similarity": r.get("similarity"),
                "lexical_rank": r.get("lexical_rank")
            })

        context = "\n\n".join(context_chunks)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict RAG assistant.\n"
                        "Use ONLY the provided context.\n"
                        "If context is insufficient, say you don't know.\n\n"
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

    except Exception:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal error")

# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():
    return {"status": "ok"}