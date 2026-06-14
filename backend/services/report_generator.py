import os
import json
import requests

from backend.services import llm_client

RULES = {
    "Dynamic Programming": "Master the 'Top-Down' vs 'Bottom-Up' approaches. Practice classic problems like Knapsack and Longest Common Subsequence.",
    "Recursion": "Strengthen your understanding of the call stack. Try solving tree-based problems without iterative loops.",
    "Machine Learning": "Focus on the bias-variance tradeoff and cross-validation techniques to improve model generalization.",
    "SQL": "Practice complex JOINS and Window Functions (OVER, PARTITION BY) for data aggregation.",
    "Algorithms": "Study time and space complexity (Big O) and practice sorting/searching implementation from scratch.",
    "Data Structures": "Implement Hash Maps and Linked Lists from scratch to understand memory allocation.",
    "Python": "Explore advanced features like Decorators, Generators, and Context Managers.",
    "System Design": "Study Horizontal vs Vertical scaling and the trade-offs of different load balancing strategies."
}

async def generate_recommendations(skill_graph, overall_score, candidate_id):
    weak_areas = skill_graph['weak_areas']
    
    # 1. Rule-based recommendations
    base_recs = []
    for skill in weak_areas:
        if skill in RULES:
            base_recs.append({
                "area": skill,
                "problem": "Limited conceptual depth observed during interview.",
                "suggestion": RULES[skill],
                "priority": "high",
                "resource_url": f"https://www.google.com/search?q={skill.replace(' ', '+')}+tutorial"
            })

    # 2. LLM recommendations (Claude)
    if llm_client.is_ai_available():
        try:
            prompt = f"""
            Generate exactly 3 specific, personalized career recommendations for a candidate.
            Results: Overall Score {overall_score}, Weak Areas: {weak_areas}, Strong Areas: {skill_graph['strong_areas']}.
            Return ONLY a JSON array:
            [
              {{
                "area": "skill name",
                "problem": "specific issue",
                "suggestion": "concrete action AND specific types of practice questions they should solve to improve this weak area",
                "priority": "high|medium|low",
                "resource_url": "link"
              }}
            ]
            """
            text_response = llm_client.call_llm(
                prompt=prompt,
                max_tokens=500,
                json_response=True
            )
            if text_response:
                # Strip markdown code fences if present
                cleaned = text_response.strip()
                if cleaned.startswith('```'):
                    cleaned = cleaned.split('```')[1]
                    if cleaned.startswith('json'):
                        cleaned = cleaned[4:]
                    cleaned = cleaned.strip()
                ai_recs = json.loads(cleaned)
                # LLM sometimes returns {"recommendations": [...]} instead of [...]
                if isinstance(ai_recs, dict):
                    for v in ai_recs.values():
                        if isinstance(v, list):
                            ai_recs = v
                            break
                    else:
                        ai_recs = []
                if isinstance(ai_recs, list):
                    return ai_recs
        except Exception as e:
            print(f"LLM Error: {e}")

    # Fallback to rule-based + placeholders if needed
    if not base_recs:
        base_recs.append({
            "area": "Technical Communication",
            "problem": "Some answers lacked structured detail.",
            "suggestion": "Use the STAR method (Situation, Task, Action, Result) to structure your responses.",
            "priority": "medium",
            "resource_url": ""
        })
        
    return base_recs[:3]
