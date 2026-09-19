from fastapi import APIRouter, HTTPException
from backend.services.scoring_engine import compute_overall_score
import json
import os
from datetime import datetime

router = APIRouter(prefix="/candidate", tags=["Candidate"])

from backend.data_utils import read_json as _read_json, get_data_dir

def read_json(filename):
    path = os.path.join(get_data_dir(), filename)
    data = _read_json(filename)
    if filename == "sessions.json":
        practice_data = _read_json("practice_sessions.json")
                
        for s in practice_data:
            s["session_type"] = "practice"
        for s in data:
            s["session_type"] = "legacy"
            
        merged = data + practice_data
        
        by_candidate = {}
        for s in merged:
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
        return merged
    elif filename == "reports.json":
        # Candidate should only see practice and legacy reports in their analytics/dashboard
        sessions = read_json("sessions.json")
        allowed_sids = {s['session_id'] for s in sessions if s.get('session_type') in ['practice', 'legacy']}
        return [r for r in data if r.get('session_id') in allowed_sids]
    return data

@router.get("/dashboard/{candidate_id}")
async def get_dashboard(candidate_id: str):
    sessions = read_json("sessions.json")
    reports = read_json("reports.json")
    
    cand_sessions = [s for s in sessions if s['candidate_id'] == candidate_id and len(s.get('answers', [])) > 0]
    
    # Filter reports: only keep reports for this candidate with answers (non-empty)
    cand_reports = [r for r in reports if r['candidate_id'] == candidate_id and len(r.get('question_results', [])) > 0]
    
    # Group by session_id and keep only the latest/most complete report per session to prevent duplicates
    latest_reports_map = {}
    for r in cand_reports:
        sid = r['session_id']
        if sid not in latest_reports_map or len(r.get('question_results', [])) > len(latest_reports_map[sid].get('question_results', [])):
            latest_reports_map[sid] = r
            
    latest_reports = list(latest_reports_map.values())
    
    overall_score = "--"
    if latest_reports:
        overall_score = round(sum(r['overall_score'] for r in latest_reports) / len(latest_reports), 1)

    # Calculate average score breakdown across all reports
    avg_conceptual = sum(r.get('score_breakdown', {}).get('conceptual', 0) for r in latest_reports) / len(latest_reports) if latest_reports else 0
    avg_practical = sum(r.get('score_breakdown', {}).get('practical', 0) for r in latest_reports) / len(latest_reports) if latest_reports else 0
    avg_behavioral = sum(r.get('score_breakdown', {}).get('behavioral', 0) for r in latest_reports) / len(latest_reports) if latest_reports else 0
    score_breakdown = {
        "conceptual": round(avg_conceptual, 1) if latest_reports else 0,
        "practical": round(avg_practical, 1) if latest_reports else 0,
        "behavioral": round(avg_behavioral, 1) if latest_reports else 0
    }

    # Generate a next step recommendation
    next_rec = "Upload your resume and start verification to calculate your score!"
    if latest_reports:
        latest_report = latest_reports[-1]
        recs = latest_report.get('recommendations', [])
        if recs and isinstance(recs, list):
            next_rec = recs[0].get('suggestion', "Continue taking interviews to refine your WCI score!")
        else:
            next_rec = "Continue taking interviews to refine your WCI score!"

    # Breakdown by skill area
    skill_scores = {}
    for r in latest_reports:
        for res in r['question_results']:
            # Find skill from session questions
            sess = next((s for s in sessions if s['session_id'] == r['session_id']), None)
            if sess:
                q = next((q for q in sess['questions'] if q['id'] == res['question_id']), None)
                if q:
                    s_name = q['skill']
                    if s_name not in skill_scores: skill_scores[s_name] = []
                    skill_scores[s_name].append(res['score'])
                    
    breakdown = [{"label": s, "score": round(sum(v)/len(v), 1)} for s, v in skill_scores.items()]

    return {
        "overall_score": overall_score,
        "interviews_completed": len(cand_sessions),
        "shortcut_alerts": sum(len(r['shortcut_flags']) for r in latest_reports),
        "reports_generated": len(latest_reports),
        "skill_breakdown": breakdown[:4],
        "score_breakdown": score_breakdown,
        "next_recommendation": next_rec,
        "recent_interviews": [
            {
                "session_id": s['session_id'],
                "date": s['start_time'].split('T')[0],
                "score": latest_reports_map[s['session_id']]['overall_score'] if s['session_id'] in latest_reports_map else (round(sum(a['score'] for a in s['answers']) / len(s['answers']), 1) if s['answers'] else "--"),
                "status": s['status'],
                "report_id": latest_reports_map[s['session_id']]['report_id'] if s['session_id'] in latest_reports_map else None,
                "skills": latest_reports_map[s['session_id']].get('skills_tested', []) if s['session_id'] in latest_reports_map else s.get('skills', []),
                "shortcut": len(latest_reports_map[s['session_id']].get('shortcut_flags', [])) > 0 if s['session_id'] in latest_reports_map else False
            } for s in cand_sessions[-5:]
        ]
    }

@router.get("/skill-graph/{candidate_id}")
async def get_skill_graph(candidate_id: str):
    from backend.services.skill_graph_builder import build_skill_graph
    sessions = read_json("sessions.json")
    cand_sessions = [s for s in sessions if s['candidate_id'] == candidate_id]
    return build_skill_graph(candidate_id, cand_sessions)


@router.get("/analytics/{candidate_id}")
async def get_analytics(candidate_id: str, range: str = "all"):
    reports = read_json("reports.json")
    
    # Filter reports with answers (non-empty)
    cand_reports = [r for r in reports if r['candidate_id'] == candidate_id and len(r.get('question_results', [])) > 0]
    
    # Sort cand_reports chronologically
    cand_reports = sorted(cand_reports, key=lambda r: r.get('created_at', ''))

    # Helper function to format timestamp beautifully
    def format_analytics_date(report):
        created_at = report.get("created_at")
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                return dt.strftime("%b %d, %I:%M %p")
            except:
                pass
        return report.get("date", "Unknown Date")

    # If the candidate has completed reports, build normal analytics
    if cand_reports:
        # Group by session_id and keep only the latest/most complete report for the sessions list table
        latest_sessions_map = {}
        for r in cand_reports:
            sid = r['session_id']
            if sid not in latest_sessions_map or len(r.get('question_results', [])) > len(latest_sessions_map[sid].get('question_results', [])):
                latest_sessions_map[sid] = r
                
        # Sort the unique session reports chronologically
        sorted_unique_reports = sorted(latest_sessions_map.values(), key=lambda r: r.get('created_at', ''))

        # Build real skill scores from skill graph
        from backend.services.skill_graph_builder import build_skill_graph
        sessions = read_json("sessions.json")
        cand_sessions = [s for s in sessions if s['candidate_id'] == candidate_id]
        graph = build_skill_graph(candidate_id, cand_sessions)
        
        real_skill_scores = {node["label"]: node["score"] for node in graph["nodes"] if node.get("tested")}
        if not real_skill_scores:
            real_skill_scores = {"Python": 85, "Algorithms": 80, "SQL": 75}

        return {
            "score_over_time": [{"date": format_analytics_date(r), "score": r['overall_score']} for r in cand_reports],
            "skill_scores": real_skill_scores,
            "behavioral_trends": {
                "dates": [format_analytics_date(r) for r in cand_reports],
                "eye_contact": [r.get('behavioral_signals', {}).get('eye_contact', 85.0) for r in cand_reports],
                "confidence": [r.get('behavioral_signals', {}).get('confidence', 75.0) for r in cand_reports],
                "speed": [r.get('behavioral_signals', {}).get('clarity', 80.0) for r in cand_reports]
            },
            "difficulty_distribution": {"easy": 10, "medium": 15, "hard": 5},
            "sessions": [
                {
                    "date": format_analytics_date(r),
                    "skills": r['skills_tested'],
                    "duration": 15,
                    "score": r['overall_score'],
                    "report_id": r['report_id']
                } for r in sorted_unique_reports
            ]
        }

    # Resilient fallback: Candidate has no completed reports with answered questions (like Saniya)
    sessions = read_json("sessions.json")
    cand_sessions = [s for s in sessions if s['candidate_id'] == candidate_id]
    
    # Fetch resume skills
    candidates = read_json("candidates.json")
    cand = next((c for c in candidates if c['user_id'] == candidate_id), None)
    skills_map = {}
    if cand and cand.get("extracted_skills"):
        # Take the top 5 skills and assign confidence scores as baseline scores
        for sk in cand["extracted_skills"][:5]:
            skills_map[sk["name"]] = sk.get("confidence", 85)
    else:
        skills_map = {"Python": 85, "Algorithms": 80, "SQL": 75}

    score_trend = []
    behavior_dates = []
    eye_contacts = []
    confidences = []
    speeds = []
    
    if cand_sessions:
        for idx, s in enumerate(cand_sessions):
            date_str = s['start_time'].split('T')[0]
            answers = s.get('answers', [])
            
            # Progressive score calculation
            prog_score = round(sum(a.get('score', 80) for a in answers) / len(answers), 1) if answers else 75.0
            
            # Dynamic credibility/integrity score based on real-time violations
            violations = s.get('proctoring_violations', [])
            cred_score = max(30, 100 - len(violations) * 12)
            
            score_trend.append({"date": f"Session {idx+1} ({date_str})", "score": prog_score})
            behavior_dates.append(f"Session {idx+1}")
            eye_contacts.append(cred_score)
            confidences.append(max(40, 85 - len(violations) * 8))
            speeds.append(82.0)
    else:
        # Absolutely clean baseline
        score_trend = [{"date": "Registration Baseline", "score": 75.0}]
        behavior_dates = ["Baseline"]
        eye_contacts = [100.0]
        confidences = [85.0]
        speeds = [80.0]

    return {
        "score_over_time": score_trend,
        "skill_scores": skills_map,
        "behavioral_trends": {
            "dates": behavior_dates,
            "eye_contact": eye_contacts,
            "confidence": confidences,
            "speed": speeds
        },
        "difficulty_distribution": {"easy": 10, "medium": 15, "hard": 5},
        "sessions": [
            {
                "date": s['start_time'].split('T')[0],
                "skills": [q.get('skill', 'Python') for q in s.get('questions', [])[:3]] if s.get('questions') else ["C", "Python", "Java"],
                "duration": 15,
                "score": round(sum(a.get('score', 75) for a in s['answers']) / len(s['answers']), 1) if s.get('answers') else "--",
                "report_id": None,
                "status": s.get("status", "in_progress")
            } for s in cand_sessions
        ]
    }

@router.get("/recommendations/{candidate_id}")
async def get_recs(candidate_id: str):
    reports = read_json("reports.json")
    cand_reports = [r for r in reports if r['candidate_id'] == candidate_id]
    if not cand_reports: return []
    return cand_reports[-1]['recommendations']

@router.get("/learning-path/{candidate_id}")
async def get_learning_path(candidate_id: str):
    reports = read_json("reports.json")
    cand_reports = [r for r in reports if r['candidate_id'] == candidate_id]
    
    if not cand_reports:
        return {
            "progress": 0,
            "milestones": [
                {"skill": "Core Python", "status": "upcoming", "score": None},
                {"skill": "Data Structures", "status": "upcoming", "score": None},
                {"skill": "System Design", "status": "upcoming", "score": None},
                {"skill": "Machine Learning", "status": "upcoming", "score": None}
            ]
        }
    
    latest = cand_reports[-1]
    progress = min(100, len(cand_reports) * 25) # Mock progress based on interview count
    
    # Map real skills from report to milestones
    milestones = []
    for skill in latest['skills_tested'][:2]:
        # Calculate avg score for this skill in the report
        scores = [q['score'] for q in latest['question_results'] if q.get('skill_area') == skill or any(k in q.get('answer_text', '').lower() for k in [skill.lower()])]
        avg = sum(scores)/len(scores) if scores else latest['overall_score']
        milestones.append({"skill": skill, "status": "completed", "score": round(avg, 1)})
    
    # Add some upcoming ones
    if len(milestones) < 4:
        milestones.append({"skill": "System Design", "status": "progress", "score": None})
        milestones.append({"skill": "Cloud Architecture", "status": "upcoming", "score": None})

    return {
        "progress": progress,
        "milestones": milestones[:4]
    }

@router.get("/official-interviews/{candidate_id}")
async def get_official_interviews(candidate_id: str):
    official = read_json("official_sessions.json")
    reports = read_json("reports.json")
    results = [s for s in official if s.get("candidate_id") == candidate_id]
    for s in results:
        if s.get("status") == "completed":
            rep = next((r for r in reports if r.get("session_id") == s.get("session_id")), None)
            if rep:
                s["report_id"] = rep.get("report_id")
                s["overall_score"] = rep.get("overall_score")
    return results

