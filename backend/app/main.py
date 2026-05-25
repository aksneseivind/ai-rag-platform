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

# ======================================================
# INIT
# ======================================================

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase environment variables")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

app = FastAPI(
    title="Borettslagsassistent API"
)

# ======================================================
# CORS
# ======================================================

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://borettslagsassistent.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ======================================================
# PREFLIGHT
# ======================================================

@app.options("/{full_path:path}")
async def preflight(full_path: str):
    return Response(status_code=200)

# ======================================================
# OPENAI
# ======================================================

EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"

def get_embedding(text: str):
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )

    return response.data[0].embedding

# ======================================================
# TEXT PROCESSING
# ======================================================

def clean_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")

    return re.sub(r"\s+", " ", text).strip()

def chunk_text(
    text,
    size=1200,
    overlap=200
):
    text = clean_text(text)

    chunks = []
    i = 0

    while i < len(text):
        chunk = text[i:i + size]

        if len(chunk.strip()) > 100:
            chunks.append(chunk)

        i += size - overlap

    return chunks

def deduplicate(chunks):
    seen = set()
    unique = []

    for chunk in chunks:
        key = chunk[:150]

        if key in seen:
            continue

        seen.add(key)
        unique.append(chunk)

    return unique

# ======================================================
# REQUEST MODELS
# ======================================================

class ChatRequest(BaseModel):
    question: str
    user_id: str

# ======================================================
# HEALTH
# ======================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "borettslagsassistent"
    }

# ======================================================
# PDF UPLOAD
# ======================================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    try:

        print("🔥 UPLOAD STARTED")

        # ======================================================
        # VALIDATE FILE
        # ======================================================

        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed"
            )

        pdf_bytes = await file.read()

        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file"
            )

        print(f"📄 FILE: {file.filename}")

        # ======================================================
        # READ PDF
        # ======================================================

        reader = PyPDF2.PdfReader(
            io.BytesIO(pdf_bytes)
        )

        pages = []

        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)

        full_text = " ".join(pages)
        full_text = clean_text(full_text)

        print(f"📊 TEXT LENGTH: {len(full_text)}")

        if len(full_text) < 50:
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from PDF"
            )

        # ======================================================
        # CHUNKING
        # ======================================================

        chunks = chunk_text(full_text)
        chunks = deduplicate(chunks)

        print(f"🧩 CHUNKS: {len(chunks)}")

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No valid chunks created"
            )

        # ======================================================
        # EMBEDDINGS
        # ======================================================

        print("⚡ CREATING EMBEDDINGS")

        embeddings = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=chunks
        )

        print("✅ EMBEDDINGS COMPLETE")

        # ======================================================
        # BUILD ROWS
        # ======================================================

        rows = []

        for i, chunk in enumerate(chunks):

            rows.append({
                "content": chunk,
                "embedding": embeddings.data[i].embedding,
                "user_id": user_id,
                "metadata": {
                    "filename": file.filename,
                    "chunk_index": i,
                    "type": "board_document"
                }
            })

        # ======================================================
        # SAVE TO SUPABASE
        # ======================================================

        print("💾 INSERTING INTO SUPABASE")

        supabase.table("chunks").insert(rows).execute()

        print("🎉 UPLOAD COMPLETE")

        return {
            "status": "success",
            "filename": file.filename,
            "chunks": len(rows)
        }

    except HTTPException:
        raise

    except Exception:
        print("❌ UPLOAD FAILED")
        print(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail="Upload failed"
        )

# ======================================================
# CHAT
# ======================================================

@app.post("/chat")
async def chat(req: ChatRequest):

    try:

        print("💬 CHAT REQUEST")
        print(f"QUESTION: {req.question}")

        # ======================================================
        # CREATE QUESTION EMBEDDING
        # ======================================================

        embedding = get_embedding(
            req.question
        )

        # ======================================================
        # VECTOR SEARCH
        # ======================================================

        result = supabase.rpc(
            "match_chunks",
            {
                "query_embedding": embedding,
                "user_id": req.user_id,
                "match_count": 8
            }
        ).execute()

        matches = result.data or []

        print(f"🔎 MATCHES FOUND: {len(matches)}")

        if not matches:
            return {
                "answer": (
                    "Fant ingen relevant informasjon "
                    "i dokumentene."
                ),
                "sources": []
            }

        # ======================================================
        # CONTEXT
        # ======================================================

        context = "\n\n".join([
            match["content"]
            for match in matches[:5]
        ])

        # ======================================================
        # SOURCES
        # ======================================================

        sources = []

        seen_files = set()

        for match in matches:

            metadata = match.get("metadata", {})

            filename = metadata.get(
                "filename",
                "ukjent"
            )

            if filename not in seen_files:
                seen_files.add(filename)

                sources.append({
                    "filename": filename
                })

        # ======================================================
        # SYSTEM PROMPT
        # ======================================================

        system_prompt = f"""
Du er en AI-assistent for et borettslag.

Svar KUN basert på informasjonen i konteksten.

REGLER:
- Ikke dikt opp regler
- Hvis informasjonen mangler:
  si tydelig at det ikke finnes i dokumentene
- Svar kort, konkret og profesjonelt
- Ikke si "basert på konteksten"

KONTEKST:
{context}
"""

        # ======================================================
        # GPT
        # ======================================================

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": req.question
                }
            ]
        )

        answer = (
            response
            .choices[0]
            .message
            .content
        )

        return {
            "answer": answer,
            "sources": sources
        }

    except Exception:
        print("❌ CHAT FAILED")
        print(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail="Chat failed"
        )