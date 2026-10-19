from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
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

class TokensReq(BaseModel):
    tokens: List[str]
    proxies: Optional[List[str]] = []

class FollowReq(BaseModel):
    streamer: str
    tokens: List[str]
    proxies: Optional[List[str]] = []

class MsgReq(BaseModel):
    streamer: str
    tokens: List[str]
    message: str
    proxies: Optional[List[str]] = []

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/validate-tokens")
async def validate_tokens(payload: TokensReq):
    results = []
    valid_count = 0
    invalid_count = 0
    
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
            
            is_valid = False
            username = "Unknown"
            
            try:
                resp = await client.get("https://kick.com/api/v1/user", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    username = data.get("username", "Unknown")
                    is_valid = True
                    valid_count += 1
                else:
                    invalid_count += 1
            except Exception:
                invalid_count += 1
                
            results.append({
                "token": t_clean,
                "valid": is_valid,
                "username": username
            })
            
    return {
        "success": True,
        "summary": {
            "validCount": valid_count,
            "invalidCount": invalid_count,
            "total": valid_count + invalid_count
        },
        "results": results
    }

@app.post("/api/follow-selected-channel")
async def follow_selected_channel(payload: FollowReq):
    followed = 0
    failed = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for t in payload.tokens:
            headers = {
                "Authorization": f"Bearer {t}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
            try:
                resp = await client.post(f"https://kick.com/api/v1/channels/{payload.streamer}/follow", headers=headers)
                if resp.status_code in [200, 201]:
                    followed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
                
    return {
        "success": True,
        "summary": {"followed": followed, "failed": failed}
    }

@app.post("/api/send-selected-bot-message")
async def send_selected_bot_message(payload: MsgReq):
    sent = 0
    failed = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for t in payload.tokens:
            headers = {
                "Authorization": f"Bearer {t}",
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {
                "content": payload.message,
                "type": "message"
            }
            try:
                resp = await client.post(f"https://kick.com/api/v2/messages/send/{payload.streamer}", json=body, headers=headers)
                if resp.status_code in [200, 201]:
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
                
    return {
        "success": True,
        "summary": {"sent": sent, "failed": failed}
    }
