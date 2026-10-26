import os
import sys
import tempfile
from pathlib import Path

# Tests never call a real AI model and never touch the real database.
os.environ["CLAIMSAATHI_DISABLE_LLM"] = "1"
os.environ["CLAIMSAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
