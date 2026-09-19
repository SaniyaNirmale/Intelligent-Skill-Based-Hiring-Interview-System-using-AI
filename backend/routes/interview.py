from fastapi import APIRouter, HTTPException
from backend.services.question_engine import get_opening_questions, get_next_question
from backend.services.answer_analyzer import analyze_answer
from backend.services.shortcut_detector import check_for_shortcuts
import uuid
from datetime import datetime
import json
import os

router = APIRouter(prefix="/interview", tags=["Interview"])

from backend.data_utils import read_json as _read_json, write_json as _write_json

def read_json(filename):
    data = _read_json(filename)
    if filename in ["sessions.json", "practice_sessions.json", "official_sessions.json"]:
        by_candidate = {}
        for s in data:
            if s.get('status') == 'in_progress':
                cid = s.get('candidate_id')
                if cid:
                    if cid not in by_candidate:
                        by_candidate[cid] = []
                    by_candidate[cid].append(s)
        modified = False
        for cid, s_list in by_candidate.items():
            if len(s_list) > 1:
                s_list.sort(key=lambda x: x.get('start_time', ''))
                for s in s_list[:-1]:
                    s['status'] = 'completed'
                    modified = True
        if modified:
            _write_json(filename, data)
    return data

def write_json(filename, data):
    _write_json(filename, data)

def get_session_by_id(session_id: str):
    # Try reading practice sessions
    practice = read_json("practice_sessions.json")
    idx = next((i for i, s in enumerate(practice) if s['session_id'] == session_id), None)
    if idx is not None:
        return practice[idx], "practice", idx

    # Try reading official sessions
    official = read_json("official_sessions.json")
    idx = next((i for i, s in enumerate(official) if s['session_id'] == session_id), None)
    if idx is not None:
        return official[idx], "official", idx

    # Try reading legacy sessions
    sessions = read_json("sessions.json")
    idx = next((i for i, s in enumerate(sessions) if s['session_id'] == session_id), None)
    if idx is not None:
        return sessions[idx], "legacy", idx

    return None, None, None

def update_session(session: dict, file_type: str, index: int):
    filename = "practice_sessions.json" if file_type == "practice" else "official_sessions.json" if file_type == "official" else "sessions.json"
    data = read_json(filename)
    data[index] = session
    write_json(filename, data)

@router.get("/active-session/{candidate_id}")
async def get_active_session(candidate_id: str, session_type: str = "practice"):
    filename = "practice_sessions.json" if session_type == "practice" else "official_sessions.json" if session_type == "official" else "sessions.json"
    sessions = read_json(filename)
    active = next((s for s in reversed(sessions) if s.get('candidate_id') == candidate_id and s.get('status') == 'in_progress'), None)
    completed = [s for s in sessions if s.get('candidate_id') == candidate_id and s.get('status') == 'completed']
    has_completed = len(completed) > 0
    if active:
        return {
            "has_active": True,
            "has_completed": has_completed,
            "session_id": active['session_id'],
            "answers_count": len(active.get('answers', [])),
            "current_index": active['current_question_index'],
            "skills": active.get('skills', [])
        }
    return {
        "has_active": False,
        "has_completed": has_completed
    }

@router.post("/start")
async def start_interview(body: dict):
    candidate_id = body.get("candidate_id")
    session_id = body.get("session_id")
    skills = body.get("skills", [])
    
    # Check candidate exists
    candidates = read_json("candidates.json")
    if not any(c['user_id'] == candidate_id for c in candidates):
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    session_type = body.get("session_type", "practice")
    
    if session_id:
        # Starting/resuming recruiter assigned official session
        official_sess, file_type, idx = get_session_by_id(session_id)
        if not official_sess:
            raise HTTPException(status_code=404, detail="Assigned interview not found")
            
        # Deactivate any pre-existing in-progress sessions for this candidate
        official_sessions = read_json("official_sessions.json")
        for s in official_sessions:
            if s['candidate_id'] == candidate_id and s['status'] == 'in_progress' and s['session_id'] != session_id:
                s['status'] = 'completed'
        write_json("official_sessions.json", official_sessions)
        
        # Reload after deactivation
        official_sess, file_type, idx = get_session_by_id(session_id)
        
        # If questions are not generated yet, generate them!
        if not official_sess.get("questions"):
            opening_q = get_opening_questions(official_sess.get("skills", ["Python"]))
            official_sess["questions"] = opening_q
        else:
            opening_q = official_sess["questions"]
            
        official_sess["status"] = "in_progress"
        official_sess["start_time"] = datetime.now().isoformat()
        
        update_session(official_sess, "official", idx)
        
        return {
            "session_id": session_id,
            "question": opening_q[official_sess.get("current_question_index", 0)],
            "total_questions": official_sess.get("total_questions", 10),
            "current_index": official_sess.get("current_question_index", 0) + 1
        }
    elif session_type == "official":
        # Starting a self-initiated official/company session
        official_sessions = read_json("official_sessions.json")
        
        # Deactivate any pre-existing in-progress sessions for this candidate
        for s in official_sessions:
            if s['candidate_id'] == candidate_id and s['status'] == 'in_progress':
                s['status'] = 'completed'
        write_json("official_sessions.json", official_sessions)
        
        official_sessions = read_json("official_sessions.json")
        
        job_role = body.get("job_role", "Software Engineer")
        difficulty = body.get("difficulty", "medium")
        
        new_session_id = str(uuid.uuid4())
        opening_q = get_opening_questions(skills)
        
        session = {
            "session_id": new_session_id,
            "candidate_id": candidate_id,
            "job_role": job_role,
            "status": "in_progress",
            "source": "job_openings",
            "current_question_index": 0,
            "total_questions": 10,
            "skills": skills,
            "questions": opening_q,
            "answers": [],
            "start_time": datetime.now().isoformat(),
            "proctoring_violations": [],
            "coding_results": [],
            "difficulty": difficulty
        }
        
        official_sessions.append(session)
        write_json("official_sessions.json", official_sessions)
        
        return {
            "session_id": new_session_id,
            "question": opening_q[0],
            "total_questions": 10,
            "current_index": 1
        }
    else:
        # Starting a free practice session
        practice_sessions = read_json("practice_sessions.json")
        
        # Deactivate any pre-existing in-progress sessions for this candidate
        for s in practice_sessions:
            if s['candidate_id'] == candidate_id and s['status'] == 'in_progress':
                s['status'] = 'completed'
        write_json("practice_sessions.json", practice_sessions)
        
        practice_sessions = read_json("practice_sessions.json")
        
        new_session_id = str(uuid.uuid4())
        opening_q = get_opening_questions(skills)
        
        session = {
            "session_id": new_session_id,
            "candidate_id": candidate_id,
            "status": "in_progress",
            "current_question_index": 0,
            "total_questions": 10,
            "skills": skills,
            "questions": opening_q,
            "answers": [],
            "start_time": datetime.now().isoformat()
        }
        
        practice_sessions.append(session)
        write_json("practice_sessions.json", practice_sessions)
        
        return {
            "session_id": new_session_id,
            "question": opening_q[0],
            "total_questions": 10,
            "current_index": 1
        }

@router.post("/answer")
async def answer_question(body: dict):
    session_id = body.get("session_id")
    answer_text = body.get("answer_text", "").strip()
    is_skipped = body.get("is_skipped", False)
    
    session, file_type, idx = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Session is not in progress")
        
    q_index = session.get("current_question_index", 0)
    questions = session.get("questions", [])
    if q_index >= len(questions):
        raise HTTPException(status_code=400, detail="No more questions in queue")
        
    current_q = questions[q_index]
    
    if is_skipped:
        analysis = {
            "score": 0.0,
            "feedback": "Question skipped by candidate.",
            "conceptual_score": 0.0,
            "detail_score": 0.0,
            "communication": {
                "clarity": 0.0,
                "logical_flow": 0.0,
                "quality": "Needs Improvement"
            },
            "behavioral": {
                "confidence": 0.0,
                "stress": 0.0,
                "emotional_stability": "Unknown"
            },
            "keywords_found": [],
            "keywords_missing": current_q.get("expected_keywords", [])
        }
    else:
        analysis = analyze_answer(
            current_q.get("text", ""),
            answer_text,
            current_q.get("expected_keywords", [])
        )
        
    ans_entry = {
        "question_id": current_q.get("id"),
        "question_text": current_q.get("text"),
        "answer_text": answer_text if not is_skipped else "[Skipped]",
        "score": analysis["score"],
        "feedback": analysis["feedback"],
        "conceptual_score": analysis["conceptual_score"],
        "detail_score": analysis["detail_score"],
        "communication": analysis["communication"],
        "behavioral": analysis["behavioral"],
        "keywords_found": analysis["keywords_found"],
        "keywords_missing": analysis["keywords_missing"]
    }
    
    if not is_skipped and answer_text:
        shortcut_flag, shortcut_reason = check_for_shortcuts(answer_text, current_q.get("text", ""))
        if shortcut_flag:
            ans_entry["shortcut_flag"] = True
            ans_entry["shortcut_reason"] = shortcut_reason
            
    session.setdefault("answers", []).append(ans_entry)
    session["current_question_index"] = q_index + 1
    
    next_q = get_next_question(session)
    if next_q:
        session.setdefault("questions", []).append(next_q)
        update_session(session, file_type, idx)
        return {
            "completed": False,
            "question": next_q,
            "current_index": session["current_question_index"] + 1,
            "total_questions": session.get("total_questions", 10)
        }
    else:
        session["status"] = "completed"
        update_session(session, file_type, idx)
        return {
            "completed": True
        }

@router.get("/resume/{session_id}")
async def resume_interview(session_id: str):
    session, file_type, idx = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.get("status") == "completed":
        return {"completed": True}
        
    if session.get("status") == "assigned":
        return {
            "completed": False,
            "status": "assigned",
            "job_role": session.get("job_role", "Software Engineer"),
            "skills": session.get("skills", []),
            "difficulty": session.get("difficulty", "medium"),
            "total_questions": session.get("total_questions", 10)
        }
        
    q_index = session.get("current_question_index", 0)
    questions = session.get("questions", [])
    
    if q_index >= len(questions) and len(questions) > 0:
        return {"completed": True}
        
    return {
        "completed": False,
        "session_id": session_id,
        "question": questions[q_index] if q_index < len(questions) else None,
        "total_questions": session.get("total_questions", 10),
        "current_index": q_index + 1,
        "status": session.get("status"),
        "job_role": session.get("job_role", "Software Engineer"),
        "skills": session.get("skills", []),
        "difficulty": session.get("difficulty", "medium")
    }


@router.post("/coding-result")
async def save_coding_result(body: dict):
    session_id = body.get("session_id")
    user_id    = body.get("user_id")
    skill      = body.get("skill", "").strip()
    score      = float(body.get("score", 0))
    passed     = bool(body.get("passed", False))

    if not skill:
        raise HTTPException(status_code=400, detail="Skill is required")

    session, file_type, idx = get_session_by_id(session_id)
    if not session and user_id:
        practice = read_json("practice_sessions.json")
        p_sess = [s for s in practice if s.get("candidate_id") == user_id]
        if p_sess:
            session, file_type, idx = p_sess[-1], "practice", practice.index(p_sess[-1])
        else:
            official = read_json("official_sessions.json")
            o_sess = [s for s in official if s.get("candidate_id") == user_id]
            if o_sess:
                session, file_type, idx = o_sess[-1], "official", official.index(o_sess[-1])
            else:
                legacy = read_json("sessions.json")
                l_sess = [s for s in legacy if s.get("candidate_id") == user_id]
                if l_sess:
                    session, file_type, idx = l_sess[-1], "legacy", legacy.index(l_sess[-1])

    if not session:
        raise HTTPException(status_code=404, detail="Session not found to attach result")

    coding_results = session.setdefault("coding_results", [])
    existing = next((i for i, r in enumerate(coding_results) if r["skill"].lower() == skill.lower()), None)
    entry = {"skill": skill, "score": score, "passed": passed}
    if existing is not None:
        coding_results[existing] = entry
    else:
        coding_results.append(entry)

    update_session(session, file_type, idx)

    coding_reports = read_json("coding_reports.json")
    coding_reports.append({
        "session_id": session["session_id"],
        "candidate_id": session.get("candidate_id"),
        "skill": skill,
        "score": score,
        "passed": passed,
        "timestamp": datetime.now().isoformat()
    })
    write_json("coding_reports.json", coding_reports)

    return {"message": f"Coding result for '{skill}' saved.", "score": score, "passed": passed}

@router.post("/proctor-violation")
async def log_proctor_violation(body: dict):
    user_id = body.get("user_id")
    session_id = body.get("session_id")
    violation = body.get("violation", "Unknown violation")
    
    session, file_type, idx = get_session_by_id(session_id)
    if not session and user_id:
        practice = read_json("practice_sessions.json")
        p_sess = [s for s in practice if s.get("candidate_id") == user_id]
        if p_sess:
            session, file_type, idx = p_sess[-1], "practice", practice.index(p_sess[-1])
        else:
            official = read_json("official_sessions.json")
            o_sess = [s for s in official if s.get("candidate_id") == user_id]
            if o_sess:
                session, file_type, idx = o_sess[-1], "official", official.index(o_sess[-1])
            else:
                legacy = read_json("sessions.json")
                l_sess = [s for s in legacy if s.get("candidate_id") == user_id]
                if l_sess:
                    session, file_type, idx = l_sess[-1], "legacy", legacy.index(l_sess[-1])
                    
    if session:
        violations = session.setdefault("proctoring_violations", [])
        violations.append(violation)
        update_session(session, file_type, idx)
        
    return {"message": "Violation logged"}
