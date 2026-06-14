import os
import json
import urllib.request
import urllib.parse
import re
import difflib
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('all-MiniLM-L6-v2')

# Load from dynamic JSON database file
TEMPLATE_ANSWERS = []
TEMPLATE_ANSWERS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "template_answers.json")

try:
    if os.path.exists(TEMPLATE_ANSWERS_FILE):
        with open(TEMPLATE_ANSWERS_FILE, "r") as f:
            data = json.load(f)
            # Flatten lists of answers under each category/skill
            for answers in data.values():
                if isinstance(answers, list):
                    TEMPLATE_ANSWERS.extend(answers)
    if not TEMPLATE_ANSWERS:
        # Fallback to defaults
        TEMPLATE_ANSWERS = [
            "A list is a mutable sequence of objects while a tuple is an immutable sequence.",
            "Hash maps use a hash function to compute an index into an array of buckets.",
            "Deadlock is a situation where two or more processes are waiting for each other to release resources.",
            "Supervised learning uses labeled data while unsupervised learning finds patterns in unlabeled data.",
            "The CAP theorem states that a distributed system can only provide two out of three guarantees.",
            "Inheritance allows a class to inherit properties and methods from another class.",
            "Polymorphism is the ability of an object to take on many forms.",
            "Encapsulation is the bundling of data and methods that operate on that data.",
            "Abstraction is the process of hiding internal details and showing only functionality.",
            "A primary key uniquely identifies a record while a foreign key links tables together."
        ]
except Exception as e:
    print(f"Error loading template answers from JSON: {e}")
    TEMPLATE_ANSWERS = [
        "A list is a mutable sequence of objects while a tuple is an immutable sequence.",
        "Hash maps use a hash function to compute an index into an array of buckets.",
        "Deadlock is a situation where two or more processes are waiting for each other to release resources.",
        "Supervised learning uses labeled data while unsupervised learning finds patterns in unlabeled data.",
        "The CAP theorem states that a distributed system can only provide two out of three guarantees.",
        "Inheritance allows a class to inherit properties and methods from another class.",
        "Polymorphism is the ability of an object to take on many forms.",
        "Encapsulation is the bundling of data and methods that operate on that data.",
        "Abstraction is the process of hiding internal details and showing only functionality.",
        "A primary key uniquely identifies a record while a foreign key links tables together."
    ]

template_embeddings = model.encode(TEMPLATE_ANSWERS)

# In-memory cache for Wikipedia lookups
WIKIPEDIA_CACHE = {}

def fetch_wikipedia_summary(query):
    """
    Queries the Wikipedia Search and Summary REST API for a technical concept/question.
    Returns the article summary/definition text.
    """
    if not query:
        return None
        
    query_clean = query.strip()
    if query_clean in WIKIPEDIA_CACHE:
        return WIKIPEDIA_CACHE[query_clean]
        
    try:
        # 1. Search Wikipedia for matching article titles
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query_clean)}&utf8=&format=json"
        req = urllib.request.Request(
            search_url, 
            headers={'User-Agent': 'WCI-Engine-ShortcutDetector/1.0 (contact: admin@wciengine.org)'}
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode('utf-8'))
            search_results = data.get("query", {}).get("search", [])
            if not search_results:
                WIKIPEDIA_CACHE[query_clean] = None
                return None
            best_title = search_results[0]["title"]
            
        # 2. Get the official summary definition
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(best_title.replace(' ', '_'))}"
        req_summary = urllib.request.Request(
            summary_url,
            headers={'User-Agent': 'WCI-Engine-ShortcutDetector/1.0 (contact: admin@wciengine.org)'}
        )
        with urllib.request.urlopen(req_summary, timeout=4) as response_summary:
            summary_data = json.loads(response_summary.read().decode('utf-8'))
            extract = summary_data.get("extract")
            WIKIPEDIA_CACHE[query_clean] = extract
            return extract
    except Exception as e:
        print(f"Error fetching Wikipedia summary for '{query_clean}': {e}")
        return None

def get_word_sequence(text):
    return re.findall(r'\b\w+\b', text.lower())

def word_sequence_similarity(text1, text2):
    words1 = get_word_sequence(text1)
    words2 = get_word_sequence(text2)
    if not words1 or not words2:
        return 0.0
    matcher = difflib.SequenceMatcher(None, words1, words2)
    return matcher.ratio()

def check_for_shortcuts(answer_text, skill=None, question_text=None):
    if not answer_text: 
        return {"is_shortcut": False, "confidence": 0}
    
    # 1. Similarity to templates (local JSON database)
    ans_emb = model.encode(answer_text)
    cos_sims = util.cos_sim(ans_emb, template_embeddings)[0]
    
    max_sim = 0.0
    reason = None
    
    # Evaluate candidates against templates with lexical guardrails
    for idx, sim in enumerate(cos_sims):
        sim_val = float(sim)
        if sim_val > 0.70:
            lex_ratio = word_sequence_similarity(answer_text, TEMPLATE_ANSWERS[idx])
            # High semantic similarity AND high lexical word sequence overlap (plagiarism)
            # OR extreme lexical overlap (verbatim copy-paste)
            if (sim_val > 0.88 and lex_ratio > 0.60) or lex_ratio > 0.75:
                if sim_val > max_sim:
                    max_sim = sim_val
                    reason = "High verbatim similarity to common template"

    # 2. Dynamic Web Lookup (Wikipedia REST API)
    web_sim = 0.0
    if not reason:
        # Search either using the question_text or the skill
        query = question_text if question_text else skill
        if query:
            web_def = fetch_wikipedia_summary(query)
            if web_def:
                # Compare candidate's answer with Wikipedia definition semantically
                web_def_emb = model.encode(web_def)
                web_sim = float(util.cos_sim(ans_emb, web_def_emb)[0][0])
                
                # Check actual sequence overlap ratio
                web_lex_ratio = word_sequence_similarity(answer_text, web_def)
                
                # Only flag as plagiarism if there is massive sequence overlap in words, 
                # protecting students who use relatable technical terms but write in their own voice
                if (web_sim > 0.86 and web_lex_ratio > 0.55) or web_lex_ratio > 0.70:
                    max_sim = max(max_sim, web_sim)
                    reason = "High verbatim similarity to dynamic web definition"

    # 3. Pattern Matching
    patterns = ["according to", "as mentioned", "the standard approach", "in summary"]
    flag_count = sum(1 for p in patterns if p in answer_text.lower())
    
    is_shortcut = (reason is not None) or (flag_count >= 2)
    
    if not reason and flag_count >= 2:
        reason = "Pattern matching flag"
        
    return {
        "is_shortcut": is_shortcut,
        "confidence": round(max(max_sim, web_sim) * 100, 1),
        "reason": reason
    }
