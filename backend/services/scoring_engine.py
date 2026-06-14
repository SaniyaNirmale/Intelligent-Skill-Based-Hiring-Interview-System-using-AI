import statistics

def compute_overall_score(session):
    if not session['answers']: return 0
    return sum(a['score'] for a in session['answers']) / len(session['answers'])

def compute_credibility_score(session):
    if not session['answers']: return 0
    base = compute_overall_score(session)
    
    # Penalize for shortcuts
    shortcuts = sum(1 for a in session['answers'] if a.get('shortcut_flag'))
    penalty = shortcuts * 15
    
    # Penalize for high variance (inconsistent knowledge)
    scores = [a['score'] for a in session['answers']]
    variance = statistics.stdev(scores) if len(scores) > 1 else 0
    variance_penalty = variance * 0.3
    
    return max(0, min(100, base - penalty - variance_penalty))

def compute_bayesian_competency(session):
    """
    Computes a Bayesian competency estimate (theta) using a Kalman Filter approach.
    Prior competency is assumed average (mean = 50, variance = 250).
    Difficulty benchmarks: easy = 35, medium = 60, hard = 85.
    As more questions are answered, uncertainty decreases, making the estimator robust to outliers.
    """
    if not session.get('answers') or not session.get('questions'):
        return 50.0

    mu = 50.0  # Prior competency mean
    sigma_sq = 250.0  # Prior uncertainty variance
    measurement_noise = 120.0  # Measurement noise for a single question evaluation

    # Benchmark benchmarks for difficulties
    difficulty_map = {'easy': 35.0, 'medium': 60.0, 'hard': 85.0}

    # Process questions sequentially to update the posterior belief
    for i, answer in enumerate(session['answers']):
        if i >= len(session['questions']):
            break
        
        q = session['questions'][i]
        diff_name = q.get('difficulty', 'medium')
        d_i = difficulty_map.get(diff_name, 60.0)
        score_i = answer.get('score', 50.0)

        # Kalman Gain (Credibility weight of new signal relative to existing uncertainty)
        K = sigma_sq / (sigma_sq + measurement_noise)

        # Update competency mean based on how candidate scored relative to current belief
        mu = mu + K * (score_i - mu)

        # Reduce uncertainty variance (belief is getting narrower and more confident)
        sigma_sq = (1 - K) * sigma_sq

    return max(0.0, min(100.0, mu))

def compute_score_breakdown(session):
    if not session['answers']: 
        return {"conceptual": 0, "practical": 0, "communication": 0, "problem_solving": 0, "behavioral": 75, "bayesian_competency": 50.0}
    
    avg_conceptual = sum(a['conceptual_score'] for a in session['answers']) / len(session['answers'])
    avg_practical = sum(a['detail_score'] for a in session['answers']) / len(session['answers'])
    
    # Module XII: Communication
    comm_scores = [a.get('communication', {}).get('clarity', 50) for a in session['answers']]
    avg_comm = sum(comm_scores) / len(comm_scores)
    
    # Module VII: Problem Solving
    ps_scores = [a['score'] for a in session['answers']]
    avg_ps = (sum(ps_scores) / len(ps_scores)) * 0.9 # Adjusted for scenario complexity
    
    # Module X: Behavioral
    beh_scores = [a.get('behavioral', {}).get('confidence', 50) for a in session['answers']]
    avg_beh = sum(beh_scores) / len(beh_scores)

    bayesian_comp = compute_bayesian_competency(session)

    return {
        "conceptual": round(avg_conceptual, 1),
        "practical": round(avg_practical, 1),
        "communication": round(avg_comm, 1),
        "problem_solving": round(avg_ps, 1),
        "behavioral": round(avg_beh, 1),
        "bayesian_competency": round(bayesian_comp, 1)
    }
