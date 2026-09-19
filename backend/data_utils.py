import os
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_mongo_client = None
_mongo_db = None

DEFAULT_MONGO_URI = "mongodb+srv://nirmalesaniya_db_user:Saniya123@cluster0.ohaepqo.mongodb.net/?retryWrites=true&w=majority"
DEFAULT_DB_NAME = "wci_engine"

def get_mongo_db():
    global _mongo_client, _mongo_db
    if _mongo_db is not None:
        return _mongo_db
    if _mongo_client is False:
        return None

    mongo_uri = os.environ.get("MONGODB_URI", DEFAULT_MONGO_URI)
    db_name = os.environ.get("MONGODB_DB_NAME", DEFAULT_DB_NAME)

    if not mongo_uri:
        _mongo_client = False
        return None

    try:
        from pymongo import MongoClient
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        _mongo_client = client
        _mongo_db = client[db_name]
        print(f"[data_utils] Connected to MongoDB Atlas database: {db_name}")
        return _mongo_db
    except Exception as e:
        print(f"[data_utils] MongoDB connection failed: {e}. Using local flat files.")
        _mongo_client = False
        return None

def get_collection_name(filename: str) -> str:
    return filename.replace(".json", "")

def sanitize_doc(doc):
    if not isinstance(doc, dict):
        return doc
    doc_copy = dict(doc)
    if "_id" in doc_copy:
        del doc_copy["_id"]
    return doc_copy

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

def _read_local_json(filename):
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

def read_json(filename):
    db = get_mongo_db()
    col_name = get_collection_name(filename)
    if db is not None:
        try:
            col = db[col_name]
            cursor = col.find({})
            docs = [sanitize_doc(d) for d in cursor]
            if docs:
                return docs
            local_data = _read_local_json(filename)
            if local_data and isinstance(local_data, list):
                docs_to_seed = [dict(d) for d in local_data]
                for d in docs_to_seed:
                    d.pop("_id", None)
                if docs_to_seed:
                    col.insert_many(docs_to_seed)
                return local_data
            return []
        except Exception as e:
            print(f"[data_utils] Error reading MongoDB collection '{col_name}': {e}")

    return _read_local_json(filename)

def write_json(filename, data):
    # Save to local file system / tmp cache
    data_dir = get_data_dir()
    path = os.path.join(data_dir, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[data_utils] Error writing local file '{filename}': {e}")

    # Sync to MongoDB Atlas collection
    db = get_mongo_db()
    col_name = get_collection_name(filename)
    if db is not None:
        try:
            col = db[col_name]
            col.delete_many({})
            if data and isinstance(data, list):
                docs_to_insert = []
                for item in data:
                    if isinstance(item, dict):
                        d = dict(item)
                        d.pop("_id", None)
                        docs_to_insert.append(d)
                if docs_to_insert:
                    col.insert_many(docs_to_insert)
        except Exception as e:
            print(f"[data_utils] Error syncing MongoDB collection '{col_name}': {e}")
