import os

folders = [
    "backend/app",
    "frontend/src",
]

files = {
    "README.md": """# AI RAG Platform v1

Production-ready RAG system for housing cooperatives and SMB.
""",

    ".gitignore": """__pycache__/
*.pyc
.env
venv/
faiss.index
*.pkl
""",

    "backend/requirements.txt": """fastapi
uvicorn
openai
python-dotenv
numpy
faiss-cpu
pypdf2
pydantic
rank-bm25
""",

    "backend/.env.example": """OPENAI_API_KEY=your_key_here
""",

    "backend/app/main.py": """from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}
""",

    "frontend/.env.example": """VITE_API_URL=http://localhost:8000
"""
}


def create_structure():
    # folders
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f"Created folder: {folder}")

    # files
    for path, content in files.items():

        dir_path = os.path.dirname(path)

        # FIX: handle root-level files like README.md
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # write file safely
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Created file: {path}")

    print("\n✅ Repo structure created successfully!")


if __name__ == "__main__":
    create_structure()