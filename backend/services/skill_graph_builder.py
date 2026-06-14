"""
skill_graph_builder.py

Builds the candidate's live Skill Graph:

  1. Every skill extracted from the resume appears as a node (pending, 0%)
  2. As the candidate completes interview questions, each answer's score is
     mapped to the question's skill and averaged across all sessions.
  3. Coding-assessment results (saved per session) additionally boost the
     skill's confidence score.
  4. Final score per skill:
       interview_avg × 0.70  +  coding_score × 0.30
     Falls back to whichever source is available if the other is absent.
"""

import json
import os
import re

DATA_DIR = "backend/data"

STOP_WORDS = {
    "and", "or", "of", "the", "for", "with", "to", "in", "on", "based",
    "systems", "system", "development", "programming", "tools", "apis", "api",
}

GENERIC_RELATION_WORDS = {
    "basic", "understanding", "familiar", "worked", "using", "good", "knowledge",
    "skill", "skills", "technology", "technologies", "concept", "concepts",
}


def _normalise_name(value: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", value or "")
    value = re.sub(r"[^a-zA-Z0-9+#.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def _skill_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (value or "").lower())
    return {t for t in tokens if len(t) > 1 and t not in STOP_WORDS}


def _relation_tokens(value: str) -> set[str]:
    return _skill_tokens(value) - GENERIC_RELATION_WORDS


def _complexity_score(node: dict) -> float:
    label = node["id"]
    tokens = _skill_tokens(label)
    score = len(tokens) * 2 + len(label) / 18
    if node.get("tested"):
        score += node.get("score", 0) / 100
    return score


def _relatedness(a: dict, b: dict) -> float:
    a_tokens = _relation_tokens(a["id"])
    b_tokens = _relation_tokens(b["id"])
    if not a_tokens or not b_tokens:
        return 0

    overlap = len(a_tokens & b_tokens) / len(a_tokens | b_tokens)
    return overlap


def _read_relationship_map() -> dict[str, list[str]]:
    path = os.path.join(DATA_DIR, "skill_relationships.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {str(parent): [str(child) for child in children] for parent, children in data.items()}


def _canonical_skill_name(name: str, canonical_names: dict[str, str]) -> str:
    key = _normalise_name(name)
    if key in canonical_names:
        return canonical_names[key]

    input_tokens = _relation_tokens(name)
    best_name = name
    best_score = 0
    for canon_key, canon_name in canonical_names.items():
        canon_tokens = _relation_tokens(canon_name)
        if not input_tokens or not canon_tokens:
            continue
        score = len(input_tokens & canon_tokens) / len(input_tokens | canon_tokens)
        if score > best_score:
            best_name = canon_name
            best_score = score

    return best_name if best_score >= 0.65 else name


def _relationship_strength(parent: dict, child: dict) -> str:
    parent_score = parent.get("score", 0)
    child_score = child.get("score", 0)
    if parent.get("tested") and child.get("tested"):
        avg = (parent_score + child_score) / 2
        if avg >= 70:
            return "strong"
        if avg < 40:
            return "weak"
    return "inferred"


def _build_dynamic_edges(nodes: list[dict], ai_dependencies: dict) -> list[dict]:
    """
    Build dependency edges from the skill relationship map and candidate data.
    The closest available parent wins, so broad parents do not connect to every
    descendant when an intermediate skill exists in the candidate graph.
    """
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    node_by_key = {_normalise_name(n["id"]): n for n in nodes}
    canonical_names = {_normalise_name(n["id"]): n["id"] for n in nodes}
    relationship_map = _read_relationship_map()

    merged_map: dict[str, list[str]] = {}
    for parent, children in relationship_map.items():
        parent_name = _canonical_skill_name(parent, canonical_names)
        merged_map.setdefault(parent_name, [])
        for child in children:
            child_name = _canonical_skill_name(child, canonical_names)
            if child_name not in merged_map[parent_name]:
                merged_map[parent_name].append(child_name)

    # Candidate-specific AI dependencies are stored as child -> prerequisites.
    # Merge them into the same parent -> child shape.
    for child, parents in (ai_dependencies or {}).items():
        child_name = _canonical_skill_name(child, canonical_names)
        for parent in parents:
            parent_name = _canonical_skill_name(parent, canonical_names)
            merged_map.setdefault(parent_name, [])
            if child_name not in merged_map[parent_name]:
                merged_map[parent_name].append(child_name)

    def add_edge(source: str, target: str):
        if _normalise_name(source) == _normalise_name(target):
            return
        source_key = _normalise_name(source)
        target_key = _normalise_name(target)
        key = (source_key, target_key)
        if key not in seen:
            parent_node = node_by_key.get(source_key, {"score": 0, "tested": False})
            child_node = node_by_key.get(target_key, {"score": 0, "tested": False})
            strength = _relationship_strength(parent_node, child_node)
            edges.append({
                "from": source,
                "to": target,
                "source": source,
                "target": target,
                "strength": strength,
            })
            seen.add(key)

    available = set(node_by_key.keys())
    parent_candidates: dict[str, list[str]] = {}
    for parent, children in merged_map.items():
        parent_key = _normalise_name(parent)
        if parent_key not in available:
            continue
        for child in children:
            child_key = _normalise_name(child)
            if child_key in available:
                parent_candidates.setdefault(child_key, []).append(parent)

    for child_key, parents in parent_candidates.items():
        child = node_by_key[child_key]
        best_parent = max(parents, key=lambda p: _complexity_score(node_by_key[_normalise_name(p)]))
        add_edge(best_parent, child["id"])

    # Keep a small similarity fallback only for literal variants like
    # "Vector Databases" and "Vector Databases Semantic Search".
    for target in nodes:
        if _normalise_name(target["id"]) in parent_candidates:
            continue
        candidates = []
        for source in nodes:
            if source["id"] == target["id"]:
                continue
            relation_score = _relatedness(source, target)
            if relation_score >= 0.65:
                candidates.append((relation_score, _complexity_score(source), source))

        candidates.sort(key=lambda item: (-item[0], item[1], item[2]["id"]))
        if candidates:
            add_edge(candidates[0][2]["id"], target["id"])

    return edges


def _read_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def build_skill_graph(candidate_id: str, all_sessions: list) -> dict:
    """
    Build the full skill graph for a candidate.

    Parameters
    ----------
    candidate_id : str
    all_sessions : list
        Every session document for this candidate (any status).

    Returns
    -------
    dict with keys: nodes, edges, inconsistencies, strong_areas, weak_areas
    """

    # ------------------------------------------------------------------
    # 1. Load candidate's extracted skills as the node seed
    # ------------------------------------------------------------------
    candidates = _read_json("candidates.json")
    candidate   = next((c for c in candidates if c["user_id"] == candidate_id), None)
    extracted   = candidate.get("extracted_skills", []) if candidate else []
    ai_dependencies = candidate.get("ai_dependencies", {}) if candidate else {}

    # Map: skill_name (lower) → { name, category }
    skill_meta: dict[str, dict] = {}
    for s in extracted:
        skill_meta[s["name"].lower()] = {
            "name":     s["name"],
            "category": s.get("category", "General Skills"),
            "confidence": s.get("confidence"),
        }

    # ------------------------------------------------------------------
    # 2. Aggregate interview scores across ALL sessions
    #    interview_scores[skill_lower] = list of float scores
    # ------------------------------------------------------------------
    interview_scores: dict[str, list[float]] = {}

    for session in all_sessions:
        questions = session.get("questions", [])
        answers   = session.get("answers",   [])

        for i, q in enumerate(questions):
            if i >= len(answers):
                break
            skill = q.get("skill", "").strip()
            if not skill:
                continue
            score = answers[i].get("score", 0)
            key   = skill.lower()
            interview_scores.setdefault(key, []).append(float(score))

    # ------------------------------------------------------------------
    # 3. Aggregate coding-assessment scores across ALL sessions
    #    coding_scores[skill_lower] = list of float scores
    # ------------------------------------------------------------------
    coding_scores: dict[str, list[float]] = {}

    for session in all_sessions:
        for cr in session.get("coding_results", []):
            skill = cr.get("skill", "").strip()
            score = cr.get("score", 0)
            if skill:
                coding_scores.setdefault(skill.lower(), []).append(float(score))

    # ------------------------------------------------------------------
    # 4. Compute final score per skill
    # ------------------------------------------------------------------
    # Collect all skill keys (extracted + any extra skills from questions)
    all_skill_keys: set[str] = set(skill_meta.keys())
    for key in interview_scores:
        all_skill_keys.add(key)
    for key in coding_scores:
        all_skill_keys.add(key)

    final_scores: dict[str, float] = {}   # skill_lower → 0-100
    score_details: dict[str, dict] = {}
    tested_skills: set[str]         = set()

    for key in all_skill_keys:
        i_scores = interview_scores.get(key, [])
        c_scores = coding_scores.get(key,   [])

        i_avg = sum(i_scores) / len(i_scores) if i_scores else None
        c_avg = sum(c_scores) / len(c_scores) if c_scores else None

        if i_avg is not None and c_avg is not None:
            final = i_avg * 0.70 + c_avg * 0.30
        elif i_avg is not None:
            final = i_avg
        elif c_avg is not None:
            final = c_avg
        else:
            final = 0.0

        if i_scores or c_scores:
            tested_skills.add(key)
            final_scores[key] = round(final, 1)
        score_details[key] = {
            "interview_score": round(i_avg, 1) if i_avg is not None else None,
            "coding_score": round(c_avg, 1) if c_avg is not None else None,
        }

    # ------------------------------------------------------------------
    # 5. Build nodes
    # ------------------------------------------------------------------
    nodes: list[dict] = []
    seen_ids: set[str] = set()

    def _make_node(name: str, category: str, score: float, tested: bool, resume_confidence=None) -> dict:
        node_category = "strong" if score > 70 else "weak" if score < 40 else "average"
        color         = "green"  if score > 70 else "red"  if score < 40 else "amber"
        details = score_details.get(name.lower(), {})
        status = node_category if tested else "pending"
        node_type = "advanced" if _complexity_score({"id": name, "tested": tested, "score": score}) >= 4 else "foundation"
        return {
            "id":       name,
            "label":    name,
            "score":    score,
            "confidence": score if tested else resume_confidence or 0,
            "resume_confidence": resume_confidence,
            "interview_score": details.get("interview_score"),
            "coding_score": details.get("coding_score"),
            "tested":   tested,
            "color":    color if tested else "grey",
            "category": status,
            "status":   status,
            "type":     node_type,
            "skill_category": category,
            "size":     int(score / 5 + 15) if tested else 15,
        }

    # Seed from extracted skills first (preserves display name + category)
    for meta in skill_meta.values():
        name  = meta["name"]
        key   = name.lower()
        score = final_scores.get(key, 0.0)
        tested = key in tested_skills
        node  = _make_node(name, meta["category"], score, tested, meta.get("confidence"))
        nodes.append(node)
        seen_ids.add(key)

    # Add any skills found in sessions but NOT in extracted list
    for key in all_skill_keys:
        if key in seen_ids:
            continue
        # Try to recover display name from sessions
        display_name = key.title()
        for session in all_sessions:
            for q in session.get("questions", []):
                if q.get("skill", "").lower() == key:
                    display_name = q["skill"]
                    break
        score  = final_scores.get(key, 0.0)
        tested = key in tested_skills
        node   = _make_node(display_name, "General Skills", score, tested)
        nodes.append(node)
        seen_ids.add(key)

    # ------------------------------------------------------------------
    # 6. Build edges (candidate-specific dependencies)
    # ------------------------------------------------------------------
    edges = _build_dynamic_edges(nodes, ai_dependencies)
    inconsistencies: list[dict] = []

    for node in []:
        skill_name = node["id"]
        
        # Dependencies are generated from candidate-specific resume data.
        prereqs = []

        for prereq in prereqs:
            # Find actual node whose label matches the prereq (case-insensitive)
            prereq_node = next(
                (n for n in nodes if n["id"].lower() == prereq.lower()), None
            )

            if prereq_node:
                edges.append({"from": prereq_node["id"], "to": skill_name})

                # Inconsistency: strong in advanced skill but weak in prereq
                if (node.get("tested") and prereq_node.get("tested")
                        and node["score"] > 70 and prereq_node["score"] < 40):
                    inconsistencies.append({
                        "skill":         skill_name,
                        "missing_prereq": prereq_node["id"],
                        "alert": (
                            f"Conceptual gap: Strong in {skill_name} "
                            f"but weak fundamentals in {prereq_node['id']}."
                        ),
                    })
            else:
                # Prereq not yet in graph — add as untested phantom node
                phantom_key = prereq.lower()
                if phantom_key not in all_node_ids:
                    phantom = {
                        "id":       prereq,
                        "label":    prereq,
                        "score":    0,
                        "tested":   False,
                        "color":    "grey",
                        "category": "pending",
                        "skill_category": "General Skills",
                        "size":     15,
                    }
                    nodes.append(phantom)
                    all_node_ids.add(phantom_key)
                edges.append({"from": prereq, "to": skill_name})

    all_node_ids = {_normalise_name(n["id"]) for n in nodes}
    for edge in list(edges):
        for endpoint in ("from", "to"):
            skill_name = edge[endpoint]
            if _normalise_name(skill_name) in all_node_ids:
                continue
            nodes.append({
                "id":       skill_name,
                "label":    skill_name,
                "score":    0,
                "confidence": 0,
                "resume_confidence": None,
                "interview_score": None,
                "coding_score": None,
                "tested":   False,
                "color":    "grey",
                "category": "pending",
                "status":   "pending",
                "type":     "foundation",
                "skill_category": "AI Suggested Foundations",
                "size":     15,
            })
            all_node_ids.add(_normalise_name(skill_name))

    node_lookup = {_normalise_name(n["id"]): n for n in nodes}
    analytical_insights: list[dict] = []
    for edge in edges:
        node = node_lookup.get(_normalise_name(edge["to"]))
        prereq_node = node_lookup.get(_normalise_name(edge["from"]))
        if (node and prereq_node and node.get("tested") and prereq_node.get("tested")
                and node["score"] > 70 and prereq_node["score"] < 40):
            alert = (
                f"Strong {node['id']} understanding detected, but weak "
                f"{prereq_node['id']} foundation."
            )
            insight = {
                "skill":          node["id"],
                "missing_prereq": prereq_node["id"],
                "alert":          alert,
            }
            inconsistencies.append(insight)
            analytical_insights.append({
                "type": "foundation_gap",
                "parent": prereq_node["id"],
                "child": node["id"],
                "message": alert,
            })

    # ------------------------------------------------------------------
    # 7. Return graph payload
    # ------------------------------------------------------------------
    tested_nodes = [n for n in nodes if n.get("tested")]
    strong_areas = [n["id"] for n in tested_nodes if n["score"] > 70]
    weak_areas   = [n["id"] for n in tested_nodes if n["score"] < 40]

    return {
        "nodes":           nodes,
        "edges":           edges,
        "inconsistencies": inconsistencies,
        "analytical_insights": analytical_insights,
        "strong_areas":    strong_areas,
        "weak_areas":      weak_areas,
    }
