import json
import os
from typing import Any, Dict, Optional

DATA_DIR = "data"
GAMES_DIR = os.path.join(DATA_DIR, "games")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")

# On s'assure que les dossiers existent au démarrage
os.makedirs(GAMES_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

def load_json(filepath: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Erreur lecture JSON {filepath}: {e}")
        return None

def save_json(filepath: str, data: Any):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # On utilise model_dump() si c'est un objet Pydantic, sinon dump direct
            if hasattr(data, 'model_dump'):
                json.dump(data.model_dump(), f, indent=4, default=str)
            elif hasattr(data, 'dict'):
                json.dump(data.dict(), f, indent=4, default=str)
            else:
                json.dump(data, f, indent=4, default=str)
    except Exception as e:
        print(f"❌ Erreur écriture JSON {filepath}: {e}")

def get_game_path(uid: str) -> str:
    return os.path.join(GAMES_DIR, f"{uid}.json")

def get_session_path(uid: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{uid}.json")