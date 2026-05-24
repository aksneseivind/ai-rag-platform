import os
import io
import re
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

app = FastAPI(title="Borettslagsassistent API")

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

# =========================================================
# TEXT PROCESSING
# =========================================================

def clean_text(text: str) -> str:
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text, size=900, overlap=150):
    text = clean_text(text)

    chunks = []
    i = 0

    while i < len(text):
        chunk = text[i:i + size]
        if len(chunk) > 80:
            chunks.append(chunk)
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
# INTENT ENGINE (Borettslag fokus)
# =========================================================

def detect_intent(q: str):
    q = q.lower()

    if any(x in q for x in ["støy", "regler", "husorden", "borettslag"]):
        return "housing_rules"

    if any(x in q for x in ["styret", "styre", "vedlikehold", "økonomi"]):
        return "board_ops"

    if any(x in q for x in ["klage", "problem", "feil", "mangel"]):
        return "issue_reporting"

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
                    "content": "Rewrite this query for semantic search in a housing association document system."
                },
                {"role": "user", "content": q}
            ],
            temperature=0
        )
        return res.choices[0].message.content
    except:
        return q

# =========================================================
# RETRIEVAL
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
# UPLOAD PDF (styredokumenter)
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
        text = clean_text(text)

        chunks = deduplicate(chunk_text(text))

        if not chunks:
            raise HTTPException(400, "No text extracted from PDF")

        embeddings = client.embeddings.create(
            model="text-embedding-3-small",
            input=chunks
        )

        rows = []
        for i, chunk in enumerate(chunks):
            rows.append({
                "content": chunk,
                "embedding": embeddings.data[i].embedding,
                "user_id": user_id,
                "metadata": {
                    "chunk_index": i,
                    "filename": file.filename,
                    "type": "board_document"
                }
            })

        supabase.table("chunks").insert(rows).execute()

        return {
            "status": "uploaded",
            "chunks": len(rows),
            "type": "board_document"
        }

    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Upload failed")

# =========================================================
# CHAT (Borettslagsassistent)
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

        rewritten_query = rewrite_query(req.question)
        query_embedding = get_embedding(rewritten_query)

        results = retrieve(
            query_embedding=query_embedding,
            user_id=req.user_id,
            k=8
        )

        if not results:
            return ChatResponse(
                answer="Jeg fant ikke relevant informasjon i borettslagets dokumenter.",
                sources=[],
                intent=intent
            )

        context_chunks = []
        sources = []
        seen = set()

        for r in results[:5]:
            content = r.get("content")
            if not content:
                continue

            key = content[:120]
            if key in seen:
                continue
            seen.add(key)

            context_chunks.append(content)

            sources.append({
                "chunk_id": r.get("id"),
                "preview": content[:200],
                "similarity": r.get("similarity"),
            })

        context = "\n\n".join(context_chunks)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du er Borettslagsassistenten.\n"
                        "Du hjelper beboere og styret med informasjon fra interne dokumenter.\n"
                        "Svar kun basert på kontekst.\n"
                        "Hvis informasjon mangler, si tydelig at det ikke står i dokumentene.\n\n"
                        f"KONTEKST:\n{context}"
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
        raise HTTPException(500, "Internal error")

# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "borettslagsassistent"
    }