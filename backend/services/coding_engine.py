import os
import json
import requests

from backend.services import llm_client

class CodingEngine:
    @staticmethod
    def generate_debugging_challenge(skill, difficulty="easy"):
        """Generates a buggy code snippet for a specific skill and difficulty."""
        import random
        topics = ["Edge Cases", "Data Type Conversions", "Off-by-one errors", "Scope and Closures", "Object/Array Mutations", "Return Statement bugs", "Null/Undefined handling", "Logical Operators"]
        topic = random.choice(topics)
        
        prompt = f"""
        Generate a 'Debugging Challenge' for a {skill} developer.
        The difficulty level should be strictly: {difficulty.upper()}.
        Focus the logical bugs specifically on the concept of: {topic}.
        The challenge should include:
        1. A piece of code (10-20 lines) with exactly 3 logical bugs (not syntax errors).
        2. A description of what the code IS SUPPOSED to do.
        Return ONLY a JSON object:
        {{
          "skill": "{skill}",
          "difficulty": "{difficulty}",
          "problem_description": "string",
          "buggy_code": "string",
          "correct_logic_explanation": "string",
          "hints": ["string"]
        }}
        """
        if llm_client.is_ai_available():
            try:
                text_response = llm_client.call_llm(
                    prompt=prompt,
                    max_tokens=600,
                    json_response=True
                )
                if text_response:
                    return json.loads(text_response.strip())
            except Exception as e:
                print(f"Error generating AI coding challenge: {e}")
                
        # Structured Fallback with actual buggy code based on language and difficulty
        skill_lower = skill.lower()
        if "python" in skill_lower:
            if difficulty == "easy":
                buggy_code = "def is_eligible(age, gpa, attendance):\n    if age > 18 and age < 25 or gpa >= 3.5 and attendance >= 90:\n        return True\n    if age < 18 and age > 25:\n        return False\n    return False"
                problem_desc = "The code determines whether a student is eligible for a scholarship based on age (18-25), GPA (>= 3.5), and attendance (>= 90%). However, operator precedence and logic conditions are buggy."
            elif difficulty == "medium":
                buggy_code = "def first_unique(s):\n    count = {}\n    for char in s:\n        count[char] = count.get(char, 0) + 1\n    for char in s:\n        if count[char] == 1:\n            return 0\n    return -1"
                problem_desc = "The following Python function is supposed to find the first non-repeating character in a string, but it fails to return the correct character index."
            else: # hard
                buggy_code = "def merge_intervals(intervals):\n    intervals.sort(key=lambda x: x[0])\n    merged = [intervals[0]]\n    for current in intervals:\n        previous = merged[-1]\n        if current[0] < previous[1]:\n            previous[1] = max(previous[1], current[1])\n        else:\n            merged.append(current)\n    return merged"
                problem_desc = "Merge overlapping intervals. There is a bug in the interval comparison condition causing incorrect overlaps."
        elif "javascript" in skill_lower or "js" in skill_lower or "react" in skill_lower:
            if difficulty == "easy":
                buggy_code = "function isEligible(age, gpa, attendance) {\n    if (age > 18 && age < 25 || gpa >= 3.5 && attendance >= 90) {\n        return true;\n    }\n    if (age < 18 && age > 25) {\n        return false;\n    }\n    return false;\n}"
                problem_desc = "Determine scholarship eligibility: age (18-25), GPA (>= 3.5), attendance (>= 90%). Operator precedence is flawed."
            elif difficulty == "medium":
                buggy_code = "function firstUnique(s) {\n    let count = {};\n    for (let char of s) {\n        count[char] = (count[char] || 0) + 1;\n    }\n    for (let char of s) {\n        if (count[char] == 1) {\n            return true;\n        }\n    }\n    return null;\n}"
                problem_desc = "Find the first non-repeating character. It returns true instead of the character."
            else: # hard
                buggy_code = "function mergeIntervals(intervals) {\n    intervals.sort((a, b) => a[0] - b[0]);\n    let merged = [intervals[0]];\n    for (let current of intervals) {\n        let previous = merged[merged.length - 1];\n        if (current[0] < previous[1]) {\n            previous[1] = Math.max(previous[1], current[1]);\n        } else {\n            merged.push(current);\n        }\n    }\n    return merged;\n}"
                problem_desc = "Merge overlapping intervals. The condition for overlapping is incorrect."
        elif "java" in skill_lower or "c" in skill_lower:
            buggy_code = "int firstUnique(char* s) {\n    int count[256] = {0};\n    for (int i = 0; s[i] != '\\0'; i++) {\n        count[s[i]]++;\n    }\n    for (int i = 0; s[i] != '\\0'; i++) {\n        if (count[s[i]] == 1) {\n            return 0;\n        }\n    }\n    return -1;\n}"
            problem_desc = "Find the first non-repeating character. Returns 0 instead of the index."
        else:
            buggy_code = f"// Buggy {skill} implementation\nfunction process() {{\n    var x = 10;\n    if (x = 5) {{\n        return true;\n    }}\n    return false;\n}}"
            problem_desc = "A basic logical check that fails due to a syntax-like logic bug."

        return {
            "skill": skill,
            "difficulty": difficulty,
            "problem_description": problem_desc,
            "buggy_code": buggy_code,
            "correct_logic_explanation": "You must find and correct the logical error causing the wrong return value.",
            "hints": ["Check what is actually being returned versus what is expected."]
        }

    @staticmethod
    def evaluate_submission(challenge, user_code):
        """Evaluates the candidate's fix using AI."""
        if llm_client.is_ai_available():
            prompt = f"""
            You are an expert technical interviewer evaluating a candidate's code fix.
            Original Skill: {challenge['skill']}
            Problem: {challenge['problem_description']}
            
            Candidate's Submitted Code:
            {user_code}
            
            Evaluate if the candidate successfully fixed the bugs and maintained optimal logic.
            Return ONLY a JSON object:
            {{
              "passed": true/false,
              "score": <0-100>,
              "feedback": "Short specific feedback on what they did right or wrong."
            }}
            """
            try:
                text_response = llm_client.call_llm(
                    prompt=prompt,
                    max_tokens=400,
                    json_response=True
                )
                if text_response:
                    return json.loads(text_response.strip())
            except Exception as e:
                print(f"Error evaluating AI code: {e}")
                
        # Simple string-based fallback evaluation
        user_lower = user_code.lower()
        has_bug = "return 0" in user_lower or "return true" in user_lower or "if (x = 5)" in user_lower
        is_passed = len(user_code.strip()) > 30 and "count" in user_lower and not has_bug
        
        return {
            "passed": is_passed,
            "score": 100 if is_passed else 30,
            "feedback": "Code evaluated via fallback rules." if is_passed else "The fix appears incomplete. Make sure you are returning the actual character/index, not a hardcoded boolean or 0."
        }

    @staticmethod
    def simulate_run(challenge, user_code):
        """Simulates running the user's code and returns mock console output/errors."""
        if llm_client.is_ai_available():
            prompt = f"""
            You are a code execution engine.
            The user submitted the following {challenge['skill']} code to solve: {challenge['problem_description']}.
            
            Code:
            {user_code}
            
            Simulate running this code with a few test cases. 
            If the code has logical bugs or syntax errors, output the exact terminal traceback or standard output showing the failure.
            If the code works, output the success logs.
            Return ONLY a JSON object:
            {{
              "output": "The raw terminal output string here (use \\n for newlines)"
            }}
            """
            try:
                text_response = llm_client.call_llm(
                    prompt=prompt,
                    max_tokens=300,
                    json_response=True,
                    speed="fast"
                )
                if text_response:
                    return json.loads(text_response.strip())
            except Exception as e:
                pass
                
        # Fallback simulated output
        user_lower = user_code.lower()
        has_bug = "return 0" in user_lower or "return true" in user_lower or "if (x = 5)" in user_lower
        is_passed = len(user_code.strip()) > 30 and "count" in user_lower and not has_bug
        
        if not is_passed:
            return {"output": "Traceback (most recent call last):\n  File \"main.py\", line 12, in <module>\n    test_output = firstUnique('aabbc')\nAssertionError: Expected 'c', but got an incorrect return value.\n\nProcess exited with code 1."}
        else:
            return {"output": "> Executing tests...\n> Test 1 ('leetcode'): Passed\n> Test 2 ('aabbc'): Passed\n> All tests passed successfully.\n\nProcess exited with code 0."}
