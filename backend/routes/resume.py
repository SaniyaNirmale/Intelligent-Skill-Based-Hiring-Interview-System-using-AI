from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from backend.services.skill_extractor import extract_skills, generate_ai_skill_dependencies
import json
import os
import PyPDF2
import io

router = APIRouter(prefix="/resume", tags=["Resume"])

DATA_DIR = "backend/data"

def read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path): return []
    with open(path, "r") as f: return json.load(f)

def write_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f: json.dump(data, f, indent=4)

def compute_ai_deps(candidate_id: str, skills: list):
    try:
        deps = generate_ai_skill_dependencies(skills)
        if deps:
            candidates = read_json("candidates.json")
            user_idx = next((i for i, u in enumerate(candidates) if u['user_id'] == candidate_id), None)
            if user_idx is not None:
                candidates[user_idx]["ai_dependencies"] = deps
                write_json("candidates.json", candidates)
    except Exception as e:
        print(f"Background AI deps error: {e}")

@router.post("/upload")
async def upload_resume(background_tasks: BackgroundTasks, file: UploadFile = File(...), candidate_id: str = Form(...)):
    ext = file.filename.split('.')[-1].lower()
    if ext not in ['pdf', 'txt', 'docx']:
        raise HTTPException(status_code=400, detail="Invalid file type. PDF, TXT, DOCX only.")

    content = await file.read()
    text = ""

    if ext == 'pdf':
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            for page in pdf_reader.pages:
                text += page.extract_text()
        except:
            raise HTTPException(status_code=400, detail="Could not parse PDF")
    elif ext == 'docx':
        try:
            import zipfile
            import re
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(content)) as docx:
                xml_content = docx.read('word/document.xml')
                try:
                    root = ET.fromstring(xml_content)
                    paragraphs = []
                    for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                        texts = [t.text for t in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if t.text]
                        paragraphs.append("".join(texts))
                    text = "\n".join(paragraphs)
                except Exception as xml_err:
                    # Fallback to regex-based paragraph extractor preserving newlines
                    xml_str = xml_content.decode('utf-8', errors='ignore')
                    paragraphs = re.findall(r'<w:p.*?>(.*?)</w:p>', xml_str, re.DOTALL)
                    p_texts = []
                    for p in paragraphs:
                        t_matches = re.findall(r'<w:t.*?>(.*?)</w:t>', p)
                        if t_matches:
                            p_texts.append("".join(t_matches))
                    text = "\n".join(p_texts)
        except Exception as e:
            print(f"DOCX extraction error: {e}")
            raise HTTPException(status_code=400, detail="Could not parse DOCX file")
    else:
        text = content.decode('utf-8', errors='ignore')

    if not text.strip():
        raise HTTPException(status_code=400, detail="File is empty or unreadable")

    results = extract_skills(text)
    
    # Update candidate
    candidates = read_json("candidates.json")
    user_idx = next((i for i, u in enumerate(candidates) if u['user_id'] == candidate_id), None)
    
    if user_idx is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    candidates[user_idx]["resume_text"] = text
    candidates[user_idx]["extracted_skills"] = results
    candidates[user_idx]["ai_dependencies"] = {}
    write_json("candidates.json", candidates)
    
    # Offload the LLM AI dependency map calculation to the background
    background_tasks.add_task(compute_ai_deps, candidate_id, results)
    
    return {
        "candidate_id": candidate_id,
        "extracted_skills": results,
        "total_found": len(results),
        "preview": text[:300] + "..."
    }

@router.get("/{candidate_id}")
async def get_resume_data(candidate_id: str):
    candidates = read_json("candidates.json")
    user = next((u for u in candidates if u['user_id'] == candidate_id), None)
    
    if not user:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    return {
        "extracted_skills": user.get("extracted_skills", []),
        "resume_text": user.get("resume_text", "")
    }

@router.delete("/{candidate_id}")
async def delete_resume(candidate_id: str):
    candidates = read_json("candidates.json")
    user_idx = next((i for i, u in enumerate(candidates) if u['user_id'] == candidate_id), None)
    
    if user_idx is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    candidates[user_idx]["resume_text"] = ""
    candidates[user_idx]["extracted_skills"] = []
    candidates[user_idx]["ai_dependencies"] = {}
    write_json("candidates.json", candidates)
    
    return {"message": "Resume and skills cleared successfully"}
