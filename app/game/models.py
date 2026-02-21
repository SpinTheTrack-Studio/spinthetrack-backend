from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
from enum import Enum


class GameStatus(str, Enum):
    LOBBY = "LOBBY"
    PLAYLIST_SELECTION = "PLAYLIST_SELECTION"
    ROUND_INTRO = "ROUND_INTRO"  # L'écran intermédiaire "Passez le téléphone à..."
    PLAYING = "PLAYING"  # Le défi est affiché/joué
    ROUND_RESULT = "ROUND_RESULT"
    FINISHED = "FINISHED"


class GameMode(str, Enum):
    CLASSIC = "CLASSIC"  # Blind Test
    MAESTRO = "MAESTRO"  # Paroles
    TWISTED = "TWISTED"  # Vitesse (si implémenté côté front)
    HUMMER = "HUMMER"  # Fredonneur


class Player(BaseModel):
    name: str
    score: int = 0
    avatar: str = "default"


class ChallengeData(BaseModel):
    mode: GameMode
    track_id: str
    track_title: str
    track_artist: str
    track_cover: str
    # Infos jeu
    question: str
    answer: str
    stream_url: str
    # Données spécifiques
    lyrics_challenge: Optional[Dict[str, Any]] = None
    playback_speed: float = 1.0


class GameState(BaseModel):
    game_id: str
    status: GameStatus = GameStatus.LOBBY
    players: List[Player] = []
    current_player_index: int = 0

    current_round: int = 0

    deck: List[Dict[str, Any]] = []
    used_tracks: List[str] = []

    current_challenge: Optional[ChallengeData] = None


class PlaylistSelectRequest(BaseModel):
    playlist_ids: List[str]


class InitGameRequest(BaseModel):
    players: List[str]
