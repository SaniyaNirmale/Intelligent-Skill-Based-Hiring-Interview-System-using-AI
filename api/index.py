import sys
import os

# Add project root to sys.path so backend.* imports work
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.main import app
from mangum import Mangum

# Vercel serverless handler — wraps the FastAPI ASGI app
handler = Mangum(app, lifespan="off")
