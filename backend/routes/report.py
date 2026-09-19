from fastapi import APIRouter, HTTPException
from backend.services.scoring_engine import compute_overall_score, compute_credibility_score, compute_score_breakdown
from backend.services.skill_graph_builder import build_skill_graph
from backend.services.report_generator import generate_recommendations
from backend.routes.interview import get_session_by_id
import uuid
from datetime import datetime
import json
import os

router = APIRouter(prefix="/report", tags=["Report"])

from backend.data_utils import read_json, write_json

@router.post("/generate")
async def generate_report(body: dict):
    session_id = body.get("session_id")
    
    session, file_type, idx = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Check if a report for this session with the exact same answer count already exists.
    reports = read_json("reports.json")
    existing = next((r for r in reports if r['session_id'] == session_id and len(r.get('question_results', [])) == len(session.get('answers', []))), None)
    if existing is not None:
        return existing
    
    # Run Engine
    overall = compute_overall_score(session)
    credibility = compute_credibility_score(session)
    breakdown = compute_score_breakdown(session)
    
    # Gather ALL sessions across practice, official, and legacy for candidate to build graph accurately
    sessions_data = read_json("sessions.json")
    practice_data = read_json("practice_sessions.json")
    official_data = read_json("official_sessions.json")
    all_sessions = sessions_data + practice_data + official_data
    
    cand_sessions = [s for s in all_sessions if s['candidate_id'] == session['candidate_id']]
    graph = build_skill_graph(session['candidate_id'], cand_sessions)
    recs = await generate_recommendations(graph, overall, session['candidate_id'])
    
    candidates = read_json("candidates.json")
    cand = next((c for c in candidates if c['user_id'] == session['candidate_id']), None)

    # Behavioral Signal Aggregation
    eye_contact = 85 + (credibility / 10) # Proxy
    confidence = breakdown.get('behavioral', 75)
    clarity = breakdown.get('communication', 80)

    # Enrich question results with question text and difficulty for candidate visibility
    enriched_answers = []
    session_questions = session.get('questions', [])
    for ans in session.get('answers', []):
        q_id = ans.get('question_id')
        q = next((q for q in session_questions if isinstance(q, dict) and q.get('id') == q_id), None)
        ans_copy = dict(ans)
        if q:
            ans_copy["text"] = q.get("text", "")
            ans_copy["difficulty"] = q.get("difficulty", "medium")
            ans_copy["expected_keywords"] = q.get("expected_keywords", [])
            ans_copy["skill"] = q.get("skill", "Unknown")
        else:
            ans_copy["text"] = "Technical Interview Question"
            ans_copy["difficulty"] = "medium"
            ans_copy["expected_keywords"] = []
            ans_copy["skill"] = "Unknown"
        enriched_answers.append(ans_copy)

    report_id = str(uuid.uuid4())
    report = {
        "report_id": report_id,
        "session_id": session_id,
        "candidate_id": session.get('candidate_id', 'unknown'),
        "name": cand.get('name', 'Unknown') if cand else "Unknown",
        "date": datetime.now().strftime("%b %d, %Y"),
        "overall_score": round(overall, 1),
        "credibility_score": round(credibility, 1),
        "score_breakdown": breakdown,
        "behavioral_signals": {
            "eye_contact": round(min(98, eye_contact), 1),
            "confidence": round(confidence, 1),
            "clarity": round(clarity, 1),
            "problem_solving": breakdown.get('problem_solving', 0)
        },
        "shortcut_flags": [a.get('shortcut_reason') for a in session.get('answers', []) if a.get('shortcut_flag')] + session.get('proctoring_violations', []),
        "recommendations": recs,
        "question_results": enriched_answers,
        "skills_tested": list(set(q.get('skill', 'Unknown') for q in session.get('questions', []) if isinstance(q, dict))),
        "created_at": datetime.now().isoformat(),
        "session_type": file_type, # Label with the respective session type (practice, official, legacy)
        "job_role": session.get("job_role", "Software Engineer")
    }
    
    reports.append(report)
    write_json("reports.json", reports)
    
    return report

@router.get("/{report_id}")
async def get_report(report_id: str):
    reports = read_json("reports.json")
    report = next((r for r in reports if r['report_id'] == report_id), None)
    if not report: raise HTTPException(status_code=404, detail="Report not found")
    
    # Dynamically resolve session_type and job_role for legacy data
    if "session_type" not in report or "job_role" not in report:
        session, file_type, _ = get_session_by_id(report.get("session_id"))
        if "session_type" not in report:
            report["session_type"] = file_type or "practice"
        if "job_role" not in report:
            report["job_role"] = session.get("job_role", "Software Engineer") if session else "Software Engineer"
            
    return report
