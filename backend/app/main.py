import os
import io
import re
import traceback

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import PyPDF2
from supabase import create_client

# =========================
# INIT
# =========================

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase env vars")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Borettslagsassistent API")

# =========================
# CORS (FIXED - NO WILDCARD DOMAINS)
# =========================

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://borettslagsassistenten.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# PRE-FLIGHT FIX
# =========================

@app.options("/{full_path:path}")
async def preflight(full_path: str):
    return Response(status_code=200)

# =========================
# OPENAI
# =========================

def get_embedding(text: str):
    return client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    ).data[0].embedding

# =========================
# TEXT
# =========================

def clean_text(text: str) -> str:
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text, size=900, overlap=150):
    text = clean_text(text)
    chunks, i = [], 0

    while i < len(text):
        chunk = text[i:i + size]
        if len(chunk) > 80:
            chunks.append(chunk)
        i += size - overlap

    return chunks


def deduplicate(chunks):
    seen, out = set(), []
    for c in chunks:
        key = c[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out

# =========================
# UPLOAD (DEBUG ADDED)
# =========================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    try:
        print("🔥 UPLOAD HIT")

        pdf_bytes = await file.read()
        print(f"📄 FILE RECEIVED: {file.filename}")

        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))

        text = " ".join([(p.extract_text() or "") for p in reader.pages])
        text = clean_text(text)

        print(f"📊 RAW TEXT LENGTH: {len(text)}")

        chunks = deduplicate(chunk_text(text))

        print(f"🧩 CHUNKS CREATED: {len(chunks)}")

        if not chunks:
            raise HTTPException(400, "No text extracted")

        print("⚡ Creating embeddings...")

        embeddings = client.embeddings.create(
            model="text-embedding-3-small",
            input=chunks
        )

        print("✅ EMBEDDINGS DONE")

        rows = [
            {
                "content": chunk,
                "embedding": embeddings.data[i].embedding,
                "user_id": user_id,
                "metadata": {
                    "chunk_index": i,
                    "filename": file.filename,
                    "type": "board_document"
                }
            }
            for i, chunk in enumerate(chunks)
        ]

        print("💾 INSERTING INTO SUPABASE...")

        supabase.table("chunks").insert(rows).execute()

        print("🎉 UPLOAD COMPLETE")

        return {
            "status": "uploaded",
            "chunks": len(rows)
        }

    except Exception as e:
        print("❌ UPLOAD FAILED")
        print(traceback.format_exc())
        raise HTTPException(500, "Upload failed")

# =========================
# CHAT (UNCHANGED)
# =========================

class ChatRequest(BaseModel):
    question: str
    user_id: str


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        embedding = get_embedding(req.question)

        res = supabase.rpc(
            "match_chunks",
            {
                "query_embedding": embedding,
                "user_id": req.user_id,
                "match_count": 8
            }
        ).execute()

        results = res.data or []

        if not results:
            return {"answer": "Fant ingen relevant informasjon."}

        context = "\n\n".join([r["content"] for r in results[:5]])

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"Bruk kun kontekst:\n{context}"
                },
                {"role": "user", "content": req.question}
            ],
            temperature=0.2
        )

        return {
            "answer": response.choices[0].message.content
        }

    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Internal error")

# =========================
# HEALTH
# =========================

@app.get("/health")
def health():
    return {"status": "ok"}