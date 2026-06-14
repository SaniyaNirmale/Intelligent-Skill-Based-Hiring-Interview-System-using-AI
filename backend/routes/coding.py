from fastapi import APIRouter, HTTPException
from backend.services.coding_engine import CodingEngine

router = APIRouter(prefix="/coding", tags=["Coding"])

@router.post("/generate")
async def generate_challenge(body: dict):
    skill = body.get("skill", "Python")
    difficulty = body.get("difficulty", "easy")
    challenge = CodingEngine.generate_debugging_challenge(skill, difficulty)
    return challenge

@router.post("/evaluate")
async def evaluate_challenge(body: dict):
    challenge = body.get("challenge")
    user_code = body.get("user_code")
    if not challenge or not user_code:
        raise HTTPException(status_code=400, detail="Missing challenge or code")
    
    result = CodingEngine.evaluate_submission(challenge, user_code)
    return result

@router.post("/run")
async def run_challenge(body: dict):
    challenge = body.get("challenge")
    user_code = body.get("user_code")
    if not challenge or not user_code:
        raise HTTPException(status_code=400, detail="Missing challenge or code")
    
    result = CodingEngine.simulate_run(challenge, user_code)
    return result
