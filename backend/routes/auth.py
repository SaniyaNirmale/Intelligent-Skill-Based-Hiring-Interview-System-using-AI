from fastapi import APIRouter, HTTPException
from backend.models.schemas import UserCreate, UserBase
import hashlib
import uuid
from datetime import datetime
import os
import json

router = APIRouter(prefix="/auth", tags=["Auth"])

from backend.data_utils import read_json, write_json

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/register")
async def register(user: UserCreate):
    candidates = read_json("candidates.json")
    recruiters = read_json("recruiters.json")
    
    # Check duplicates
    if any(u['email'] == user.email for u in candidates + recruiters):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    hashed = hash_password(user.password)
    
    new_user = {
        "user_id": user_id,
        "name": user.name,
        "email": user.email,
        "password_hash": hashed,
        "role": user.role,
        "created_at": datetime.now().isoformat()
    }
    
    if user.role == "candidate":
        new_user["extracted_skills"] = []
        candidates.append(new_user)
        write_json("candidates.json", candidates)
    else:
        new_user["company"] = "WCI Engine Partner"
        recruiters.append(new_user)
        write_json("recruiters.json", recruiters)
        
    return {"user_id": user_id, "name": user.name, "email": user.email, "role": user.role}

@router.post("/login")
async def login(credentials: dict):
    email = credentials.get("email")
    password = credentials.get("password")
    role = credentials.get("role")
    
    file = "candidates.json" if role == "candidate" else "recruiters.json"
    users = read_json(file)
    
    user = next((u for u in users if u['email'] == email), None)
    
    if not user or user['password_hash'] != hash_password(password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {
        "user_id": user['user_id'],
        "name": user['name'],
        "email": user['email'],
        "role": user['role'],
        "token": f"wci-{user['user_id']}"
    }

@router.get("/me")
async def get_me(user_id: str, role: str):
    file = "candidates.json" if role == "candidate" else "recruiters.json"
    users = read_json(file)
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Return without password hash
    return {k: v for k, v in user.items() if k != "password_hash"}
