from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.routes import auth, resume, interview, report, candidate, recruiter, coding
from backend.services.scoring_engine import compute_overall_score
import json
import os
import asyncio
import random
import base64
from datetime import datetime
from fastapi import Response

app = FastAPI(title="WCI Engine API", version="1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

# Mount Routers
app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(report.router)
app.include_router(candidate.router)
app.include_router(recruiter.router)
app.include_router(coding.router)

# Serve Frontend Static Files
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path), name="frontend")

from fastapi.responses import RedirectResponse

from backend.data_utils import read_json, write_json, get_data_dir, get_snapshots_dir

@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/frontend/index.html")

@app.get("/recruiter/snapshot/{session_id}")
async def get_snapshot(session_id: str):
    snapshots_dir = get_snapshots_dir()
    path = os.path.join(snapshots_dir, f"{session_id}.jpg")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return Response(content=f.read(), media_type="image/jpeg")
    return Response(status_code=404)

# WebSocket State
connected_recruiters = {}
connected_candidates = {}

@app.websocket("/ws/candidate/{session_id}")
async def candidate_socket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    connected_candidates[session_id] = websocket
    snapshots_dir = get_snapshots_dir()
    try:
        while True:
            data = await websocket.receive_json()
            
            # Real-time snapshot saving for the live monitor
            if data.get("type") == "snapshot" and "image" in data:
                try:
                    img_data = data["image"].split(",")[1]
                    snapshot_file = os.path.join(snapshots_dir, f"{session_id}.jpg")
                    with open(snapshot_file, "wb") as f:
                        f.write(base64.b64decode(img_data))
                except: pass

            if session_id in connected_recruiters:
                for recruiter_ws in connected_recruiters[session_id]:
                    await recruiter_ws.send_json(data)
    except WebSocketDisconnect:
        if session_id in connected_candidates:
            del connected_candidates[session_id]

@app.websocket("/ws/recruiter/{session_id}")
async def recruiter_monitor(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in connected_recruiters:
        connected_recruiters[session_id] = []
    connected_recruiters[session_id].append(websocket)
    
    try:
        while True:
            # Receive commands from recruiter (like "nudge")
            data = await websocket.receive_json()
            if data.get("type") == "nudge_candidate":
                if session_id in connected_candidates:
                    await connected_candidates[session_id].send_json({"type": "alert", "message": "Please seat yourself properly in front of the camera."})
            
            # Keep-alive or handle other recruiter inputs
    except WebSocketDisconnect:
        connected_recruiters[session_id].remove(websocket)

# Initialize Data Files
DATA_FILES = ["candidates.json", "recruiters.json", "sessions.json", "reports.json", "practice_sessions.json", "official_sessions.json", "coding_reports.json", "job_roles.json"]
data_dir = get_data_dir()
for f in DATA_FILES:
    file_path = os.path.join(data_dir, f)
    if not os.path.exists(file_path):
        if f == "job_roles.json":
            default_jobs = [
                {
                    "role_id": "job_dev_01",
                    "title": "Backend Developer",
                    "description": "Develop scalable backend services, design robust database models, and construct secure high-throughput REST APIs.",
                    "skills": ["Python", "FastAPI", "SQL"],
                    "difficulty": "medium",
                    "num_questions": 10
                },
                {
                    "role_id": "job_mle_02",
                    "title": "Machine Learning Engineer",
                    "description": "Architect deep learning pipelines, train neural networks, fine-tune LLMs, and optimize real-time inference.",
                    "skills": ["Python", "Machine Learning", "PyTorch", "LLMs"],
                    "difficulty": "hard",
                    "num_questions": 10
                },
                {
                    "role_id": "job_fed_03",
                    "title": "Frontend Developer",
                    "description": "Design sleek, glassmorphic interfaces, establish styling standards, and orchestrate performant SPA components.",
                    "skills": ["React", "JavaScript", "CSS", "HTML"],
                    "difficulty": "easy",
                    "num_questions": 10
                }
            ]
            write_json(f, default_jobs)
        else:
            write_json(f, [])

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
