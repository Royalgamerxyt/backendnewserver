from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import httpx
from cryptography.fernet import Fernet

app = FastAPI(title="ClassicAgentBot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
FERNET_KEY = os.getenv("FERNET_KEY")
if not FERNET_KEY:
    FERNET_KEY = Fernet.generate_key().decode()
fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Token(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    token_enc = Column(String, nullable=False)
    username = Column(String, nullable=True)
    status = Column(String, default="active")
    added_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

class AddTokensReq(BaseModel):
    tokens: List[str]

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/add-tokens")
async def add_tokens(payload: AddTokensReq):
    db = SessionLocal()
    
    # Naye tokens aane par purane saare tokens aur unke usernames delete ho jayenge
    db.query(Token).delete()
    db.commit()
    
    added = 0
    ids = []
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for t in payload.tokens:
            t_clean = t.strip()
            if not t_clean:
                continue
            
            headers = {
                "Authorization": f"Bearer {t_clean}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            }
            
            fetched_username = None
            token_status = "active"
            
            try:
                # Kick API se real username fetch karna
                resp = await client.get("https://kick.com/api/v1/user", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    fetched_username = data.get("username")
                else:
                    token_status = "invalid"
            except Exception:
                token_status = "error"

            enc = fernet.encrypt(t_clean.encode()).decode()
            
            tok = Token(
                token_enc=enc, 
                username=fetched_username, 
                status=token_status,
                added_at=datetime.utcnow()
            )
            db.add(tok)
            db.commit()
            db.refresh(tok)
            ids.append(tok.id)
            added += 1
            
    db.close()
    return {"success": True, "added": added, "ids": ids}

@app.get("/api/list-tokens")
def list_tokens():
    db = SessionLocal()
    rows = db.query(Token).all()
    out = [
        {
            "id": r.id, 
            "username": r.username if r.username else f"Account #{r.id}", 
            "status": r.status
        } 
        for r in rows
    ]
    db.close()
    return {"tokens": out}
