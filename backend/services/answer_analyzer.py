from sentence_transformers import SentenceTransformer, util
import numpy as np
import json
from backend.services.llm_client import is_ai_available, call_llm

model = SentenceTransformer('all-MiniLM-L6-v2')

def analyze_answer(question_text, answer_text, expected_keywords):
    if not answer_text or len(answer_text.split()) < 5:
        return {
            "score": 0,
            "feedback": "Please provide a more detailed and specific answer.",
            "conceptual_score": 0,
            "detail_score": 0,
            "communication": {
                "clarity": 0,
                "logical_flow": 0,
                "quality": "Needs Improvement"
            },
            "behavioral": {
                "confidence": 0,
                "stress": 100,
                "emotional_stability": "High Stress"
            },
            "keywords_found": [],
            "keywords_missing": expected_keywords
        }

    # If LLM is available, perform rich dynamic evaluation
    if is_ai_available():
        system_prompt = (
            "You are an expert technical interviewer and senior software engineer. Evaluate the candidate's answer to the technical question. "
            "You must return a raw JSON object containing the evaluation. Do NOT wrap it in any Markdown code fences or extra text. "
            "The JSON keys must be exactly:\n"
            "- \"score\": integer from 0 to 100\n"
            "- \"feedback\": a highly personalized assessment (3-4 sentences) analyzing the candidate's actual answer content. Specifically point out what they answered correctly, what they got wrong or missed, and what concrete technical concepts they should improve.\n"
            "- \"conceptual_score\": integer 0 to 100\n"
            "- \"detail_score\": integer 0 to 100\n"
            "- \"clarity\": integer 0 to 100\n"
            "- \"logical_flow\": integer 0 to 100\n"
            "- \"confidence\": integer 0 to 100\n"
            "- \"stress\": integer 0 to 100\n"
            "- \"keywords_found\": list of strings (which expected keywords are present in the answer)\n"
            "- \"keywords_missing\": list of strings (which expected keywords are missing or poorly explained)"
        )
        
        prompt = (
            f"Question: {question_text}\n"
            f"Expected Keywords: {expected_keywords}\n"
            f"Candidate's Answer: {answer_text}\n\n"
            "Analyze the candidate's answer. Give a balanced, highly specific review. Highlight their correct points, explain any misconceptions or incorrect ideas, and give specific technical improvements. Be encouraging but precise."
        )
        
        response = call_llm(prompt, system_prompt=system_prompt, json_response=True)
        if response:
            try:
                res_data = json.loads(response)
                score = round(float(res_data.get("score", 50)), 1)
                clarity = round(float(res_data.get("clarity", 50)), 1)
                logical_flow = round(float(res_data.get("logical_flow", 50)), 1)
                confidence = round(float(res_data.get("confidence", 50)), 1)
                stress = round(float(res_data.get("stress", 50)), 1)
                
                return {
                    "score": score,
                    "feedback": res_data.get("feedback", "Good response."),
                    "conceptual_score": round(float(res_data.get("conceptual_score", 50)), 1),
                    "detail_score": round(float(res_data.get("detail_score", 50)), 1),
                    "communication": {
                        "clarity": clarity,
                        "logical_flow": logical_flow,
                        "quality": "High" if clarity > 80 else "Moderate" if clarity > 50 else "Needs Improvement"
                    },
                    "behavioral": {
                        "confidence": confidence,
                        "stress": stress,
                        "emotional_stability": "Stable" if stress < 35 else "Hesitant" if stress < 65 else "High Stress"
                    },
                    "keywords_found": res_data.get("keywords_found", []),
                    "keywords_missing": res_data.get("keywords_missing", [])
                }
            except Exception as e:
                print(f"[Answer Analyzer] Error parsing LLM JSON: {e}. Falling back to rule-based analysis.")

    # 1. Keyword Coverage
    found = [k for k in expected_keywords if k.lower() in answer_text.lower()]
    missing = [k for k in expected_keywords if k not in found]
    coverage = len(found) / len(expected_keywords) if expected_keywords else 1.0

    # 2. Semantic Similarity
    reference = f"The answer to {question_text} involves {', '.join(expected_keywords)}."
    embeddings = model.encode([answer_text, reference])
    similarity = float(util.cos_sim(embeddings[0], embeddings[1])[0][0])

    # 3. Detail Score (Word count based)
    word_count = len(answer_text.split())
    detail = min(word_count / 80, 1.0) # Max score at 80 words

    # 4. Module XII: Communication Analysis
    sentences = [s.strip() for s in answer_text.split('.') if s.strip()]
    clarity_score = min(len(sentences) / 4, 1.0) * 100 # Measures structure
    logical_score = min(max(similarity * 1.2, 0.4), 1.0) * 100 # Proxy for technical logic
    
    # 5. Module X: Behavioral Simulation (Confidence/Stress)
    confidence = (similarity * 0.7 + detail * 0.3) * 100
    stress_level = max(0, 100 - confidence)

    # Final Weighted Score (Composite of Tech + Comm)
    tech_score = (0.5 * coverage + 0.5 * similarity) * 100
    comm_score = (0.6 * logical_score + 0.4 * clarity_score)
    final_score = (0.7 * tech_score + 0.3 * comm_score)
    final_score = max(0, min(100, final_score))

    # Generate Dynamic Feedback
    feedback_parts = []
    if final_score >= 80:
        feedback_parts.append("Excellent response! You demonstrated strong conceptual understanding of the topic.")
        if found:
            feedback_parts.append(f"Your explanation successfully integrated core concepts such as {', '.join(found)}.")
    elif final_score >= 50:
        if found:
            feedback_parts.append(f"Good attempt. You correctly identified and discussed {', '.join(found[:2])}.")
            if len(found) < len(expected_keywords):
                feedback_parts.append("However, your explanation was somewhat incomplete.")
        else:
            feedback_parts.append("Your response touched on some correct ideas, but lacked technical precision and core terminology.")
    else:
        feedback_parts.append("Your answer lacked the necessary depth or missed the core concepts.")

    if missing:
        if len(missing) == 1:
            feedback_parts.append(f"To improve your answer, you should discuss '{missing[0]}' in detail.")
        else:
            feedback_parts.append(f"To improve, make sure to explain concepts like '{missing[0]}' and '{missing[1]}' and how they relate to the question.")

    if clarity_score < 40 and word_count > 10:
        feedback_parts.append("Try to break your response into clearer, more structured sentences to improve communication.")
        
    if stress_level > 60:
        feedback_parts.append("Ensure you articulate your technical points confidently and avoid hesitant phrasing.")

    feedback = " ".join(feedback_parts)

    return {
        "score": round(final_score, 1),
        "feedback": feedback,
        "conceptual_score": round(similarity * 100, 1),
        "detail_score": round(detail * 100, 1),
        "communication": {
            "clarity": round(clarity_score, 1),
            "logical_flow": round(logical_score, 1),
            "quality": "High" if comm_score > 80 else "Moderate" if comm_score > 50 else "Needs Improvement"
        },
        "behavioral": {
            "confidence": round(confidence, 1),
            "stress": round(stress_level, 1),
            "emotional_stability": "Stable" if stress_level < 30 else "Hesitant" if stress_level < 60 else "High Stress"
        },
        "keywords_found": found,
        "keywords_missing": missing
    }
