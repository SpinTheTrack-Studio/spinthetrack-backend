import json
import os
import random
import requests
from fastapi import APIRouter, HTTPException, Header, Body, Query
from fastapi.responses import StreamingResponse
from Crypto.Cipher import Blowfish

from app.game.models import GameState, GameStatus, GameMode, Player, PlaylistSelectRequest, ChallengeData, \
    InitGameRequest
from app.game.services import DeezerGameService
from app.utils.file_manager import load_json, save_json, get_game_path, get_session_path

router = APIRouter(prefix="/game", tags=["Game Logic"])


# --- DEPENDANCES (HELPERS) ---

def get_arl_from_session(uid: str) -> str:
    session_path = get_session_path(uid)
    session_data = load_json(session_path)
    if not session_data or "arl" not in session_data:
        raise HTTPException(401, "Session invalide ou expirée (ARL manquant)")
    return session_data["arl"]


def get_game_state(uid: str) -> GameState:
    game_path = get_game_path(uid)
    game_data = load_json(game_path)
    if not game_data:
        raise HTTPException(404, "Aucune partie trouvée pour cet ID")
    return GameState(**game_data)


def save_game_state(uid: str, game: GameState):
    game_path = get_game_path(uid)
    save_json(game_path, game)


# --- CŒUR DU SYSTÈME : GÉNÉRATEUR DE DÉFIS ---

async def generate_challenge(game: GameState, service: DeezerGameService, game_id: str) -> ChallengeData:
    """
    Gère un challenge complet :
    - Choisit le mode (Classic, Maestro, Twisted, Last Word).
    - Configure l'URL audio (Full, Preview 45s, ou Full avec start_time).
    - Configure la vitesse de lecture (Twisted).
    """
    if not game.deck:
        raise HTTPException(400, "Le deck est vide, impossible de générer un défi.")

    track = game.deck.pop(0)
    game.used_tracks.append(track['id'])

    modes = [GameMode.CLASSIC, GameMode.MAESTRO, GameMode.LAST_WORD, GameMode.TWISTED]
    selected_mode = random.choice(modes)

    challenge = ChallengeData(
        mode=selected_mode,
        track_id=track['id'],
        track_title=track['title'],
        track_artist=track['artist'],
        track_cover=track.get('album_cover', ''),
        question="",
        answer="",
        stream_url="",
        playback_speed=1.0
    )

    track_duration = int(track.get('duration', 180))

    # --- LOGIQUE SPÉCIFIQUE PAR MODE ---

    # CAS A : MAESTRO
    if selected_mode == GameMode.MAESTRO:
        lyrics = service.get_synced_lyrics_challenge(track['id'], track_duration)
        if lyrics:
            challenge.question = f"Complétez après : '{lyrics['previous_line']}'"
            challenge.answer = lyrics['hidden_answer']
            challenge.lyrics_challenge = lyrics
            challenge.stream_url = f"/api/game/stream/full/{track['id']}?game_id={game_id}"
        else:
            selected_mode = random.choice([GameMode.CLASSIC, GameMode.TWISTED])
            challenge.mode = selected_mode

    # CAS B : LE MOT DE LA FIN
    if selected_mode == GameMode.LAST_WORD:
        last_word_data = await service.generate_last_word_challenge_jit(track['id'], track_duration)
        if last_word_data:
            challenge.question = last_word_data['question']
            challenge.answer = last_word_data['expected_answer']
            # On passe le timestamp de départ dans l'URL du stream
            start_time = last_word_data['timestamp_start']
            challenge.stream_url = f"/api/game/stream/full/{track['id']}?game_id={game_id}&start_time={start_time}"
        else:
            # Fallback si pas de lyrics exploitables
            selected_mode = random.choice([GameMode.CLASSIC, GameMode.TWISTED])
            challenge.mode = selected_mode

    # CAS C : CLASSIC ou TWISTED (Fallback inclus)
    if selected_mode in [GameMode.CLASSIC, GameMode.TWISTED]:
        challenge.stream_url = f"/api/game/stream/preview/{track['id']}?game_id={game_id}"

        if selected_mode == GameMode.CLASSIC:
            challenge.question = "Trouvez le titre et/ou l'artiste !"
            challenge.answer = f"{track['artist']} - {track['title']}"

        elif selected_mode == GameMode.TWISTED:
            speed = random.choice([0.5, 1.5])
            challenge.playback_speed = speed
            label = "Accéléré" if speed > 1 else "Ralenti"
            challenge.question = f"Titre ({label}) ?"
            challenge.answer = track['title']

    return challenge


# --- ROUTES DE GESTION DE PARTIE ---

@router.post("/init")
async def init_game(data: InitGameRequest, x_game_id: str = Header(..., alias="X-Game-ID")):
    get_arl_from_session(x_game_id)
    player_objs = [Player(name=p) for p in data.players]
    new_game = GameState(
        game_id=x_game_id,
        players=player_objs,
        status=GameStatus.PLAYLIST_SELECTION
    )
    save_game_state(x_game_id, new_game)
    return {"status": "success", "game_id": x_game_id, "state": new_game}


@router.post("/end")
async def end_game(x_game_id: str = Header(..., alias="X-Game-ID")):
    file_path = os.path.join("data", "games", f"{x_game_id}.json")
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success", "message": "La partie a bien été terminée et les données supprimées."}
        else:
            return {"status": "warning", "message": "Fichier introuvable, la partie est probablement déjà terminée."}
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Erreur lors de la suppression des données de la partie : {str(e)}")


@router.get("/state")
async def get_state(x_game_id: str = Header(..., alias="X-Game-ID")):
    return get_game_state(x_game_id)


@router.post("/setup/playlists")
async def select_playlists(data: PlaylistSelectRequest, x_game_id: str = Header(..., alias="X-Game-ID")):
    game = get_game_state(x_game_id)
    arl = get_arl_from_session(x_game_id)
    service = DeezerGameService(arl)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "data", "cards.json")
    if not os.path.exists(file_path):
        if os.path.exists("cards.json"):
            file_path = "cards.json"
        else:
            raise HTTPException(404, "Base de données cards.json introuvable.")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            full_library = json.load(f)
    except:
        raise HTTPException(500, "Base de données corrompue.")

    flat_deck = []
    loaded_playlists = []

    for pl_name, cards in full_library.items():
        if not cards: continue
        first_card = next(iter(cards.values()))
        pid = str(first_card.get('playlist_id'))

        if pid in data.playlist_ids:
            loaded_playlists.append(pl_name)
            for c in cards.values():
                flat_deck.append({
                    "id": c.get('id'),
                    "title": c.get('title'),
                    "artist": c.get('artist'),
                    "album_cover": c.get('cover'),
                    "duration": c.get('duration', 180)
                })

    if not flat_deck:
        raise HTTPException(400, "Aucune playlist trouvée avec ces IDs.")

    random.shuffle(flat_deck)
    game.deck = flat_deck
    game.current_round = 1
    game.current_player_index = 0
    game.status = GameStatus.ROUND_INTRO

    game.current_challenge = await generate_challenge(game, service, x_game_id)
    save_game_state(x_game_id, game)

    return {
        "status": "success",
        "deck_size": len(flat_deck),
        "playlists_loaded": loaded_playlists
    }


@router.post("/round/next")
async def next_round(result: dict = Body(...), x_game_id: str = Header(..., alias="X-Game-ID")):
    SCORE_TO_WIN = 10
    game = get_game_state(x_game_id)
    arl = get_arl_from_session(x_game_id)
    service = DeezerGameService(arl)

    if result.get("win"):
        game.players[game.current_player_index].score += 1

    winner_found = any(p.score >= SCORE_TO_WIN for p in game.players)
    if winner_found or not game.deck:
        game.status = GameStatus.FINISHED
        game.current_challenge = None
        game.players.sort(key=lambda p: p.score, reverse=True)
        save_game_state(x_game_id, game)
        return {"status": "finished", "state": game}

    game.current_player_index = (game.current_player_index + 1) % len(game.players)
    game.current_round += 1
    game.status = GameStatus.ROUND_INTRO
    game.current_challenge = await generate_challenge(game, service, x_game_id)

    save_game_state(x_game_id, game)
    return {"status": "success", "state": game}


# --- SYSTÈME DE STREAMING AUDIO (HACK V6) ---

def stream_deezer_content(url, sng_id, service, start_byte=0):
    headers = {}
    if start_byte > 0:
        headers['Range'] = f'bytes={start_byte}-'

    with requests.get(url, stream=True, headers=headers) as r:
        r.raise_for_status()
        bf_key = service.generate_blowfish_key(sng_id)
        iv = b"\x00\x01\x02\x03\x04\x05\x06\x07"
        chunk_size = 2048 * 3
        for chunk in r.iter_content(chunk_size=chunk_size):
            if not chunk: break
            if len(chunk) >= 2048:
                cipher = Blowfish.new(bf_key, Blowfish.MODE_CBC, iv)
                decrypted = cipher.decrypt(chunk[:2048])
                chunk = decrypted + chunk[2048:]
            yield chunk


@router.get("/stream/full/{track_id}")
async def stream_full_track(track_id: str, game_id: str = Query(...), start_time: float = Query(0.0)):
    """
    Route pour les modes MAESTRO et LE MOT DE LA FIN.
    Accepte un start_time optionnel (en secondes) pour sauter à un moment précis.
    """
    arl = get_arl_from_session(game_id)
    service = DeezerGameService(arl)
    url, sng_id, _ = service.get_full_track_url(track_id)

    if not url:
        raise HTTPException(404, "Stream introuvable chez Deezer")

    # Calcul du saut (seek) si start_time est fourni
    start_byte = 0
    if start_time > 0:
        # MP3 128kbps = env. 16000 octets / seconde
        target_byte = start_time * 16000
        # Alignement sur un bloc de chiffrement (6144 octets)
        block_align = 6144
        start_byte = int((target_byte // block_align) * block_align)

    return StreamingResponse(
        stream_deezer_content(url, sng_id, service, start_byte=start_byte),
        media_type="audio/mpeg"
    )


@router.get("/stream/preview/{track_id}")
async def stream_preview_track(track_id: str, game_id: str = Query(...)):
    """
    Route pour les modes CLASSIC/TWISTED.
    Stream le fichier maître mais saute directement à 45 secondes.
    """
    arl = get_arl_from_session(game_id)
    service = DeezerGameService(arl)
    url, sng_id, _ = service.get_full_track_url(track_id)

    if not url:
        raise HTTPException(404, "Stream introuvable chez Deezer")

    start_seconds = 45
    target_byte = start_seconds * 16000
    block_align = 6144
    start_byte = (target_byte // block_align) * block_align

    return StreamingResponse(
        stream_deezer_content(url, sng_id, service, start_byte=start_byte),
        media_type="audio/mpeg"
    )


# --- VUE JSON POUR LE MENU ---

@router.get("/playlists")
async def get_available_playlists():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "data", "cards.json")

    if not os.path.exists(file_path):
        if os.path.exists("cards.json"):
            file_path = "cards.json"
        else:
            raise HTTPException(404, "cards.json introuvable.")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            full_data = json.load(f)

        light_playlists = {}
        for pl_name, cards in full_data.items():
            if not cards: continue
            cards_list = list(cards.values())
            all_tags = set()
            all_covers = []

            for card in cards_list:
                if "tags" in card and isinstance(card["tags"], list):
                    all_tags.update(card["tags"])
                if card.get("cover"):
                    all_covers.append(card["cover"])

            random.shuffle(all_covers)
            playlist_id = cards_list[0].get('playlist_id', -1)

            light_playlists[pl_name] = {
                "id": playlist_id,
                "title": pl_name,
                "track_count": len(cards),
                "covers": all_covers[:4],
                "tags": list(all_tags)
            }

        return light_playlists
    except json.JSONDecodeError:
        raise HTTPException(500, "Fichier cards.json corrompu.")
