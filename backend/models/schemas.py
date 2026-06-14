from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: str

class UserCreate(UserBase):
    password: str

class CandidateProfile(UserBase):
    user_id: str
    resume_text: Optional[str] = None
    extracted_skills: List[Dict] = []
    created_at: str

class RecruiterProfile(UserBase):
    user_id: str
    company: Optional[str] = "WCI Engine Partner"
    created_at: str

class QuestionItem(BaseModel):
    id: str
    text: str
    difficulty: str
    skill_area: str
    expected_keywords: List[str]

class AnswerItem(BaseModel):
    question_id: str
    answer_text: str
    score: float
    feedback: str
    conceptual_score: float
    detail_score: float
    shortcut_flag: bool
    time_taken: int

class InterviewSession(BaseModel):
    session_id: str
    candidate_id: str
    status: str  # in_progress, completed
    current_question_index: int
    total_questions: int
    questions: List[QuestionItem]
    answers: List[AnswerItem] = []
    start_time: str

class SkillReport(BaseModel):
    report_id: str
    session_id: str
    candidate_id: str
    name: str
    date: str
    overall_score: float
    credibility_score: float
    score_breakdown: Dict[str, float]
    behavioral_signals: Dict[str, float]
    shortcut_flags: List[str]
    recommendations: List[Dict]
    question_results: List[Dict]
    skills_tested: List[str]
    created_at: str
