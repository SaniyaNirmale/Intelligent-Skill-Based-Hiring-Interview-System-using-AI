import re
import spacy
import json
from sentence_transformers import SentenceTransformer, util
from backend.services import llm_client

# ---------------------------------------------------------------------------
# SKILLS_DICTIONARY – used ONLY for:
#   1. Mapping a resume category name → a standardised display name
#   2. Phase-2 fallback when NO skills section is found in the resume
# ---------------------------------------------------------------------------
SKILLS_DICTIONARY = {
    "Programming Languages": ["Python", "Java", "JavaScript", "TypeScript", "C++", "C", "Go", "Rust", "SQL", "R", "PHP", "Swift", "Kotlin", "Scala", "Ruby", "Dart"],
    "Frontend Development": ["React", "Vue.js", "Angular", "HTML", "CSS", "Tailwind CSS", "Redux", "Next.js", "Svelte", "HTML5", "CSS3"],
    "Backend & APIs": ["Node.js", "FastAPI", "Django", "Flask", "Spring Boot", "Express", "GraphQL", "REST APIs", "RESTful APIs", "API Integration"],
    "AI & Machine Learning": ["Machine Learning", "Deep Learning", "NLP", "Computer Vision", "TensorFlow", "PyTorch", "Scikit-learn", "Transfer Learning", "LangChain", "LangGraph", "FAISS", "Hugging Face", "RAG", "Transformers", "Prompt Engineering"],
    "Database Systems": ["PostgreSQL", "MongoDB", "MySQL", "Redis", "Elasticsearch", "Firebase", "SQLite", "Relational Databases", "Vector Databases"],
    "Cloud & DevOps": ["AWS", "Docker", "Kubernetes", "GCP", "Azure", "CI/CD", "Terraform", "Jenkins", "Git", "GitHub"],
    "CS Fundamentals": ["Data Structures", "Algorithms", "OOP", "OOPs", "System Design", "Operating Systems", "Networking", "Computer Networks"]
}

# -------------------------------------------------------------------------
# Resume section header keywords – when we encounter one of these headers
# AFTER the skills section starts, we stop collecting skill lines.
# -------------------------------------------------------------------------
STOP_SECTION_HEADERS = {
    "education", "projects", "project", "experience", "work experience",
    "internship", "internships", "publications", "certifications", "certificates",
    "certificate", "summary", "objective", "achievements", "awards", "courses",
    "languages", "interests", "strengths", "declaration", "patents", "references",
    "additional information", "co-curricular activities", "extracurricular",
    "accomplishments", "honors", "volunteer", "activities"
}

# -------------------------------------------------------------------------
# Skill section header keywords – used to detect where skills start
# -------------------------------------------------------------------------
SKILL_SECTION_HEADERS = {
    "skills", "technical skills", "skill set", "expertise", "technologies",
    "core competencies", "competencies", "key skills", "skills & tools",
    "tools & technologies", "technical expertise", "technical proficiency"
}

# -------------------------------------------------------------------------
# Normalisation: map messy lower-cased variants to a clean display name
# -------------------------------------------------------------------------
NORMALIZATION_MAP = {
    "oops": "OOP",
    "oop s": "OOP",
    "oops (object-oriented programming)": "OOP",
    "react js": "React",
    "react.js": "React",
    "reactjs": "React",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "restful apis": "REST APIs",
    "restful api": "REST APIs",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "restapi": "REST APIs",
    "api integration": "API Integration",
    "jwt authentication": "JWT Authentication",
    "jwt auth": "JWT Authentication",
    "jwt": "JWT Authentication",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "transfer learning": "Transfer Learning",
    "prompt engineering": "Prompt Engineering",
    "multi-agent systems": "Multi-Agent Systems",
    "multi agent systems": "Multi-Agent Systems",
    "hugging face": "Hugging Face",
    "relational databases": "Relational Databases",
    "vector databases": "Vector Databases",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "langsmith": "LangSmith",
    "data structures": "Data Structures",
    "operating systems": "Operating Systems",
    "computer networks": "Computer Networks",
    "workflow automation": "Workflow Automation",
    "json handling": "JSON Handling",
    "embedding-based retrieval": "Embedding-Based Retrieval",
    "embedding based retrieval": "Embedding-Based Retrieval",
    "llm apis": "LLM APIs",
    "llm api": "LLM APIs",
}

# -------------------------------------------------------------------------
# Load NLP models once at import time
# -------------------------------------------------------------------------
try:
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

model = SentenceTransformer('all-MiniLM-L6-v2')

# Pre-compute embeddings for the fallback dictionary (used in Phase 3 only)
all_flat_skills = [s for sub in SKILLS_DICTIONARY.values() for s in sub]
skill_embeddings = model.encode(all_flat_skills)


# -------------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------------

def normalize_skill_name(raw: str) -> str:
    """Return a clean, consistently-capitalised skill name."""
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', raw).strip()
    lower = cleaned.lower()

    # 1. Exact map lookup
    if lower in NORMALIZATION_MAP:
        return NORMALIZATION_MAP[lower]

    # 2. Match against the flat skills dictionary (case-insensitive)
    for s in all_flat_skills:
        if s.lower() == lower:
            return s

    # 3. Generic title-case as a last resort
    if cleaned.isupper() or cleaned.islower():
        return cleaned.title()

    return cleaned


def _is_section_header(line: str) -> bool:
    """Return True if *line* looks like a resume section header."""
    # strip bullets / leading whitespace
    stripped = line.strip().lstrip("•*-▪o➢❖\uf0b7\u2022\u25aa\u2756 \t")
    upper = stripped.upper()
    # All-caps short header (up to ~30 chars)
    if stripped.isupper() and 2 <= len(stripped) <= 30:
        return True
    # Well-known header words
    lowered = stripped.lower().rstrip(":").strip()
    return lowered in STOP_SECTION_HEADERS | SKILL_SECTION_HEADERS


def _is_skills_start(line: str) -> bool:
    """Return True if *line* marks the beginning of the skills section."""
    stripped = line.strip().lstrip("•*-▪o➢❖\uf0b7\u2022\u25aa\u2756 \t")
    lowered = stripped.lower().rstrip(":").strip()
    return lowered in SKILL_SECTION_HEADERS or "skill" in lowered.split()


def _is_stop_section(line: str) -> bool:
    """Return True if *line* marks the start of a non-skill section."""
    stripped = line.strip().lstrip("•*-▪o➢❖\uf0b7\u2022\u25aa\u2756 \t")
    lowered = stripped.lower().rstrip(":").strip()
    # Must be short (not a sentence), uppercased OR in the known list
    if len(stripped.split()) > 5:
        return False
    return lowered in STOP_SECTION_HEADERS or (stripped.isupper() and lowered in STOP_SECTION_HEADERS)


# -------------------------------------------------------------------------
# PHASE 1: Isolate the SKILLS section and parse category bullet lines
# -------------------------------------------------------------------------

def _extract_skills_section_lines(text: str) -> list[str]:
    """
    Scan the raw resume text and return only the lines that belong to the
    Skills / Technical Skills section.  Lines are returned in original order.
    """
    raw_lines = text.split("\n")
    in_skills = False
    skills_lines = []

    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue  # skip blank lines

        # Detect entry into the skills section
        if not in_skills and _is_skills_start(stripped):
            in_skills = True
            # Don't append the header line itself – it contains no skill data
            continue

        if in_skills:
            # Detect exit: another major section starts
            if _is_stop_section(stripped):
                break  # stop collecting
            skills_lines.append(stripped)

    return skills_lines


def _group_wrapped_lines(lines: list[str]) -> list[str]:
    """
    PDF/DOCX text extraction often wraps long bullet lines across multiple
    raw lines.  This function merges continuation lines with their header.

    A line is treated as a NEW entry (not a continuation) if it:
    - starts with a bullet marker  (•, *, –, ▪ …)
    - contains a colon that looks like  "Category: ..."
    - is all-caps (section header guard – shouldn't appear here but just in case)
    """
    BULLET_RE = re.compile(r'^[•*\-▪o➢❖\uf0b7\u2022\u25aa\u2756]')
    HEADER_RE = re.compile(r'^[^:]{2,50}:\s*\S')  # "Category: skill1, ..."

    grouped = []
    for line in lines:
        is_new = (
            bool(BULLET_RE.match(line))
            or bool(HEADER_RE.match(line))
            or (line.isupper() and len(line) <= 30)
        )
        if is_new or not grouped:
            grouped.append(line)
        else:
            # continuation – append with a space
            grouped[-1] = grouped[-1].rstrip() + " " + line.strip()

    return grouped


def _parse_category_line(line: str) -> tuple[str, list[str]] | None:
    """
    Parse a single skill bullet line of the form:
        • Category Name: Skill A, Skill B, Skill C
        • Category Name - Skill A, Skill B
        Category Name: Skill A, Skill B

    Returns (category, [skill, ...]) or None if the line cannot be parsed.
    """
    # Strip bullet chars
    cleaned = line.strip().lstrip("•*-▪o➢❖\uf0b7\u2022\u25aa\u2756 \t")

    # Try "Category: skills" split
    match = re.match(r'^([^:\-]{2,60})(?::|(?:\s+\-\s+))(.+)$', cleaned)
    if not match:
        return None

    category_raw = match.group(1).strip()
    skills_raw = match.group(2).strip()

    # Split skills by comma or semicolon
    parts = re.split(r'[,;]', skills_raw)
    skills = []
    for p in parts:
        p = p.strip()
        # Remove leading "and / or / &"
        p = re.sub(r'(?i)^(?:and|or|&)\s+', '', p).strip()
        # Remove trailing periods
        p = re.sub(r'\.\s*$', '', p).strip()
        # Remove parenthetical notes that are very long (they are usually explanations, not skill names)
        # but keep short ones like "(Basic)" or "(NoSQL)"
        # Filter: non-empty, reasonable length
        if p and 1 <= len(p) < 80 and p.lower() not in ('and', 'or', 'etc', 'none', 'n/a', 'nil', '&'):
            skills.append(p)

    if not skills:
        return None

    return category_raw, skills


def _map_category(category_raw: str) -> str:
    """
    Map a resume category label to a standardised display name using
    fuzzy keyword matching.  If nothing matches, return a title-cased
    version of the original label.

    Order is critical: more specific / narrower matches come FIRST so that
    a category like "Gen AI, LLMs & Frameworks" doesn't get swallowed by
    the broad 'ai' check before the embedded/IoT check has a chance.
    """
    cl = category_raw.lower()
    cl_clean = re.sub(r'[^a-z0-9 ]', '', cl)

    # --- Most-specific checks first ---
    if any(k in cl_clean for k in ['program', 'coding lang', 'scripting lang']):
        return "Programming Languages"

    if any(k in cl_clean for k in ['core cs', 'cs concept', 'cs fundamental', 'computer science concept', 'dsa']):
        return "CS Fundamentals"

    if any(k in cl_clean for k in ['backend', 'api develop', 'server side']):
        return "Backend & APIs"

    if any(k in cl_clean for k in ['web tech', 'web develop', 'frontend', 'front end', 'ui tech', 'javascript framework']):
        return "Frontend Development"

    # Web Development (Saniya-style) → Frontend Development
    if 'web' in cl_clean and 'develop' in cl_clean:
        return "Frontend Development"

    if any(k in cl_clean for k in ['database', ' db', 'data store', 'data storage', 'sql']):
        return "Database Systems"

    if any(k in cl_clean for k in ['cloud', 'devops', 'infra', 'deploy', 'cicd', 'ci cd']):
        return "Cloud & DevOps"

    # Embedded / IoT BEFORE generic AI so that "Arduino, Sensors..." stays here
    if any(k in cl_clean for k in ['embedded', 'iot', 'microcontroller', 'hardware', 'sensor integration', 'arduino', 'robotics']):
        return "Embedded Systems & IoT"

    # Gen AI section (e.g. "Gen AI, LLMs & Frameworks") → own category
    if any(k in cl_clean for k in ['gen ai', 'generative ai', 'llm', 'large language']):
        return "Gen AI & LLMs"

    # Generic AI / ML AFTER all the above
    if any(k in cl_clean for k in ['machine learning', 'deep learning', 'artificial intel', ' ai ', 'nlp', ' ml ']):
        return "AI & Machine Learning"
    if cl_clean.startswith('ai') or cl_clean.endswith(' ai'):
        return "AI & Machine Learning"

    # Match against known SKILLS_DICTIONARY keys
    for dict_cat in SKILLS_DICTIONARY:
        dc = re.sub(r'[^a-z0-9 ]', '', dict_cat.lower())
        if dc in cl_clean or cl_clean in dc:
            return dict_cat

    # Fall back – title-case the original label exactly as written
    return category_raw.title()


# -------------------------------------------------------------------------
# MAIN ENTRY POINT
# -------------------------------------------------------------------------

def extract_skills(text: str) -> list[dict]:
    """
    Extract skills from resume text.

    Strategy:
      Phase 1 – Dynamically parse the Skills section bullet lines.
                 If this yields ≥ 1 skill, we STOP here (no false positives).
      Phase 2 – Dictionary keyword search across the whole resume (fallback
                 only when Phase 1 found nothing – i.e. no Skills section).
      Phase 3 – Semantic similarity search (additional fallback).
    """
    found_skills: list[dict] = []

    # ---- PHASE 1: Dynamic Skills Section Parsing -------------------------
    section_lines = _extract_skills_section_lines(text)
    grouped_lines = _group_wrapped_lines(section_lines)

    for line in grouped_lines:
        parsed = _parse_category_line(line)
        if parsed is None:
            continue
        category_raw, skill_list = parsed
        mapped_cat = _map_category(category_raw)

        for skill_name in skill_list:
            norm = normalize_skill_name(skill_name)
            # De-duplicate within phase 1
            if not any(s['name'].lower() == norm.lower() for s in found_skills):
                found_skills.append({
                    "name": norm,
                    "confidence": 95,
                    "category": mapped_cat
                })

    # If Phase 1 succeeded, return immediately – no global scan needed.
    if found_skills:
        return sorted(found_skills, key=lambda x: x['confidence'], reverse=True)

    # ---- PHASE 2: Dictionary keyword fallback (whole-resume scan) --------
    # Only runs when the resume has NO parseable Skills section.
    text_lower = text.lower()
    for category, skills in SKILLS_DICTIONARY.items():
        for skill in skills:
            skill_lower = skill.lower()
            if len(skill_lower) <= 2:
                # Short tokens (C, R, Go) – require strict word boundaries
                pattern = rf'(?<![a-zA-Z0-9]){re.escape(skill_lower)}(?![a-zA-Z0-9])'
                matched = bool(re.search(pattern, text_lower))
            else:
                matched = skill_lower in text_lower

            if matched:
                norm = normalize_skill_name(skill)
                if not any(s['name'].lower() == norm.lower() for s in found_skills):
                    found_skills.append({
                        "name": norm,
                        "confidence": 90,
                        "category": category
                    })

    # ---- PHASE 3: Semantic similarity (whole-resume, deep fallback) ------
    if nlp and not found_skills:
        try:
            doc = nlp(text)
            candidates = list(set([
                chunk.text.lower().strip()
                for chunk in doc.noun_chunks
                if 3 < len(chunk.text) < 35
            ]))[:50]
            if candidates:
                cand_embeddings = model.encode(candidates, convert_to_tensor=True)
                cosine_scores = util.cos_sim(cand_embeddings, skill_embeddings)
                for i in range(len(candidates)):
                    best_idx = int(cosine_scores[i].argmax())
                    score = float(cosine_scores[i][best_idx])
                    if score > 0.88:
                        skill_name = all_flat_skills[best_idx]
                        found_cat = "General Skills"
                        for cat, sl in SKILLS_DICTIONARY.items():
                            if skill_name in sl:
                                found_cat = cat
                                break
                        if not any(s['name'].lower() == skill_name.lower() for s in found_skills):
                            found_skills.append({
                                "name": skill_name,
                                "confidence": int(score * 100),
                                "category": found_cat
                            })
        except Exception as e:
            print(f"[skill_extractor] Semantic phase error: {e}")

    # De-duplicate and sort
    unique_skills: list[dict] = []
    seen: set[str] = set()
    for s in found_skills:
        key = s['name'].lower()
        if key not in seen:
            unique_skills.append(s)
            seen.add(key)

    return sorted(unique_skills, key=lambda x: x['confidence'], reverse=True)

def generate_ai_skill_dependencies(skills_list: list[dict]) -> dict:
    """
    Given a list of extracted skills, use the LLM to dynamically generate a dependency map.
    Returns: {"SkillA": ["Prereq1", "Prereq2"], ...}
    """
    if not llm_client.is_ai_available() or not skills_list:
        return {}

    skill_names = [s['name'] for s in skills_list]
    prompt = f"""
    You are an expert software architecture analyzer.
    Given this list of skills extracted from a candidate's resume:
    {skill_names}
    
    Determine the direct prerequisite skills or core foundational technologies for EACH of these skills. 
    You may include foundational skills that are NOT in the list (e.g., if 'React' is in the list, 'JavaScript' is a prerequisite).
    Do NOT include more than 2-3 prerequisites per skill.
    
    Return ONLY a single valid JSON dictionary where the keys are the exact skill names from the list, and the values are a list of prerequisite strings.
    Example:
    {{
      "LangChain": ["Python", "Machine Learning"],
      "React": ["JavaScript", "HTML"]
    }}
    """
    try:
        response = llm_client.call_llm(prompt=prompt, max_tokens=1000, json_response=True)
        if response:
            data = json.loads(response)
            return data
    except Exception as e:
        print(f"[skill_extractor] Error generating AI skill dependencies: {e}")
        
    return {}
