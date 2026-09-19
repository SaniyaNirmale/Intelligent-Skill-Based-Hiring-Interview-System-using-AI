import os
import json

def get_data_dir():
    if os.environ.get("VERCEL"):
        path = "/tmp/backend/data"
    else:
        path = "backend/data"
    os.makedirs(path, exist_ok=True)
    return path

def get_snapshots_dir():
    path = os.path.join(get_data_dir(), "snapshots")
    os.makedirs(path, exist_ok=True)
    return path

def read_json(filename):
    data_dir = get_data_dir()
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        local_path = os.path.join("backend/data", filename)
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def write_json(filename, data):
    data_dir = get_data_dir()
    path = os.path.join(data_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
