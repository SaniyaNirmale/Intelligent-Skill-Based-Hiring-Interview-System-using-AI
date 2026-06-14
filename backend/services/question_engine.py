import json
import random
import os
import uuid
import requests

QUESTIONS_PATH = "backend/data/questions_bank.json"
from backend.services import llm_client

def load_questions():
    if not os.path.exists(QUESTIONS_PATH): return []
    with open(QUESTIONS_PATH, "r") as f: return json.load(f)

def generate_ai_question(skill: str, difficulty: str, asked_texts: list):
    """
    Dynamically generates a custom technical interview question using Claude/Anthropic API.
    """
    if not llm_client.is_ai_available():
        return None
        
    prompt = f"""
    You are an expert technical interviewer.
    Generate a highly realistic theoretical/conceptual interview question for a developer on the skill: '{skill}'.
    CRITICAL: This is a spoken interview. DO NOT ask the candidate to write code, build programs, or solve programming algorithms. Ask theoretical, architectural, or conceptual questions only.
    The question must target the difficulty level: '{difficulty}'.
    Avoid these previously asked questions: {asked_texts}.
    
    Return ONLY a single, valid JSON object with the following structure (no other text, markdown blocks or explanations):
    {{
      "id": "dynamic_{uuid.uuid4().hex[:8]}",
      "text": "The actual question text, professional and clear.",
      "skill": "{skill}",
      "difficulty": "{difficulty}",
      "expected_keywords": ["keyword1", "keyword2", "keyword3"]
    }}
    """
    
    try:
        text_response = llm_client.call_llm(
            prompt=prompt,
            max_tokens=400,
            json_response=True
        )
        if text_response:
            data = json.loads(text_response.strip())
            return data
    except Exception as e:
        print(f"Error generating AI question for {skill}: {e}")
        
    return None

def generate_local_fallback_question(skill: str, difficulty: str):
    """
    Generates a localized fallback question if the offline bank has no direct match
    and the AI key is offline.
    """
    templates = {
        "easy": [
            "Explain the basic syntax, core concepts, and data structures in {skill}.",
            "What are the main advantages and common use cases of {skill}?",
            "What is the difference between a local and global variable scope in {skill}?"
        ],
        "medium": [
            "How does {skill} handle error catching, exceptions, and resource management?",
            "Explain how the execution context and lifecycle operations work in {skill}.",
            "What are the standard design patterns and modular components in {skill}?"
        ],
        "hard": [
            "Describe the internal memory model, performance optimization, and concurrent behaviors in {skill}.",
            "Explain how you would architect a highly scalable, high-throughput system using {skill}.",
            "What are the critical security vulnerabilities and optimization techniques when deploying {skill} at scale?"
        ]
    }
    
    keywords_map = {
        "easy": ["basics", "syntax", "advantages", "concepts", skill.lower()],
        "medium": ["exception", "context", "modules", "patterns", "error handling", skill.lower()],
        "hard": ["scalability", "concurrency", "performance", "optimization", "vulnerability", skill.lower()]
    }
    
    selected_text = random.choice(templates.get(difficulty, templates['medium']))
    text = selected_text.format(skill=skill)
    keywords = keywords_map.get(difficulty, keywords_map['medium'])
    
    return {
        "id": f"fallback_{uuid.uuid4().hex[:6]}",
        "text": text,
        "skill": skill,
        "difficulty": difficulty,
        "expected_keywords": keywords
    }

def get_opening_questions(skills: list):
    """
    Returns 3 starting questions. Uses Claude/AI dynamic generation if key is present,
    or falls back to local bank matching and dynamic fallback template generators.
    """
    opening_questions = []
    
    # Generate 3 initial easy questions
    for i in range(3):
        # Cycle through candidate skills if multiple exist
        skill_obj = skills[i % len(skills)] if skills else "General Software"
        skill_name = skill_obj['name'] if isinstance(skill_obj, dict) else str(skill_obj)
        
        # 1. Try AI generation
        q = None
        if llm_client.is_ai_available():
            q = generate_ai_question(skill_name, "easy", [x['text'] for x in opening_questions])
            
        # 2. Try bank matching if AI fails/offline
        if not q:
            all_q = load_questions()
            match_q = [x for x in all_q if x['difficulty'] == 'easy' and x['skill'].lower() == skill_name.lower() and x not in opening_questions]
            if match_q:
                q = random.choice(match_q)
                
        # 3. Fallback to local dynamic template generator
        if not q:
            q = generate_local_fallback_question(skill_name, "easy")
            
        opening_questions.append(q)
        
    return opening_questions

def get_next_question(session_data):
    """
    Retrieves the next adaptive question based on previous score results.
    Generates new questions dynamically via AI or template engine.
    """
    asked_ids = [a['question_id'] for a in session_data['answers']]
    
    # Complete interview after 10 questions
    if len(asked_ids) >= 10:
        return None

    last_answer = session_data['answers'][-1] if session_data['answers'] else None
    last_difficulty = session_data['questions'][session_data['current_question_index']]['difficulty']
    
    # Adaptive Difficulty Logic
    new_difficulty = last_difficulty
    if last_answer:
        if last_answer['score'] > 70:
            if last_difficulty == 'easy': new_difficulty = 'medium'
            elif last_difficulty == 'medium': new_difficulty = 'hard'
        elif last_answer['score'] < 40:
            if last_difficulty == 'hard': new_difficulty = 'medium'
            elif last_difficulty == 'medium': new_difficulty = 'easy'

    # Determine which skill to ask next (round-robin cycle of tested skills)
    skills = session_data.get('skills', ['General Software'])
    if not skills:
        skills = ['General Software']
    skill_index = len(asked_ids) % len(skills)
    skill_obj = skills[skill_index]
    skill_name = skill_obj['name'] if isinstance(skill_obj, dict) else str(skill_obj)

    # 1. Try AI generation
    q = None
    asked_texts = [x.get('text', '') for x in session_data['questions']]
    if llm_client.is_ai_available():
        q = generate_ai_question(skill_name, new_difficulty, asked_texts)

    # 2. Try offline bank matching
    if not q:
        all_q = load_questions()
        candidates = [x for x in all_q if x['id'] not in asked_ids and x['difficulty'] == new_difficulty and x['skill'].lower() == skill_name.lower()]
        if candidates:
            q = random.choice(candidates)

    # 3. Fallback to local dynamic template generator
    if not q:
        q = generate_local_fallback_question(skill_name, new_difficulty)

    return q
