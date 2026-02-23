import json
import os
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from app.auth.services import get_arl_from_api

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Dossier sécurisé pour les tokens (ne pas envoyer ce contenu au front !)
SESSIONS_DIR = os.path.join('data', 'sessions')


class LoginRequest(BaseModel):
    email: str
    password: str


def save_user_session(game_id: str, arl: str):
    """Sauvegarde l'ARL dans un fichier privé lié à l'ID du jeu"""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    # Nettoyage de l'ID pour sécurité
    clean_id = "".join(x for x in game_id if x.isalnum() or x in "-_")
    file_path = os.path.join(SESSIONS_DIR, f"{clean_id}.json")

    with open(file_path, "w") as f:
        json.dump({"arl": arl}, f)


@router.post("/login")
async def login_headless(
        data: LoginRequest,
        x_game_id: str = Header(..., alias="X-Game-ID")  # On récupère l'ID unique du front
):
    print(f"Tentative de connexion pour la session : {x_game_id}")

    # 1. Appel à Playwright (Headless)
    arl = await get_arl_from_api(data.email, data.password)

    if not arl:
        raise HTTPException(status_code=401, detail="Échec de l'authentification Deezer")

    # 2. Stockage Persistant par utilisateur
    try:
        save_user_session(x_game_id, arl)
    except Exception as e:
        print(f"Erreur écriture session: {e}")
        raise HTTPException(status_code=500, detail="Erreur sauvegarde session")

    # 3. Réponse (On ne renvoie PAS l'ARL au front pour sécurité maximale)
    return {"status": "success", "message": "Session Deezer active"}
