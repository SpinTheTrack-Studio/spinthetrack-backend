import binascii
import hashlib
import os
import random
from typing import Optional, Tuple, Dict, Any

import requests
import urllib3
from Crypto.Cipher import AES
from dotenv import load_dotenv
from groq import AsyncGroq

# --- CONFIGURATION ---
BLOWFISH_SECRET = "g4el58wc0zvf9na1"
AES_KEY_MOBILE = b"jo6aey6haid2Teih"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cache-Control": "no-cache",
    "Referer": "https://www.deezer.com/"
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# Initialisation du client Groq asynchrone
groq_client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))


class DeezerGameService:
    def __init__(self, arl: str):
        self.session = requests.Session()
        self.session.cookies.set('arl', arl, domain='.deezer.com')
        self.session.headers.update(HEADERS)
        self.api_token = None
        self.license_token = None
        self._init_session()

    def _init_session(self):
        print("🕵️  [Service] Init Session (Mode Web HTML5)...")
        try:
            params = {
                "method": "deezer.getUserData",
                "api_version": "1.0",
                "api_token": "null",
                "input": "3"
            }
            r = self.session.get("https://www.deezer.com/ajax/gw-light.php", params=params, timeout=10)
            data = r.json()
            if 'results' not in data:
                print("❌ ARL invalide.")
                return
            self.api_token = data['results']['checkForm']
            self.license_token = data['results']['USER']['OPTIONS']['license_token']
            print(f"✅ Connecté (ID: {data['results']['USER'].get('USER_ID')})")

        except Exception as e:
            print(f"❌ Erreur Init Session: {e}")

    def get_synced_lyrics_challenge(self, track_id: str, duration: int) -> Optional[Dict[str, Any]]:
        """
        Récupère les paroles synchronisées DIRECTEMENT depuis Deezer.
        """
        if not self.api_token:
            return None
        try:
            params = {
                "method": "song.getLyrics",
                "api_version": "1.0",
                "api_token": self.api_token
            }
            r = self.session.post(
                "https://www.deezer.com/ajax/gw-light.php",
                params=params,
                json={"sng_id": str(track_id)},
                timeout=10
            )
            data = r.json()
            if 'results' not in data or not data['results'].get('LYRICS_SYNC_JSON'):
                print(f"⚠️ Pas de paroles synchronisées sur Deezer pour {track_id}")
                return None

            sync_data = data['results']['LYRICS_SYNC_JSON']

            lines = []
            for item in sync_data:
                line_text = item.get("line", "").strip()
                if line_text:
                    timestamp = int(item.get("milliseconds", 0)) / 1000.0
                    lines.append({"time": timestamp, "text": line_text})

            if len(lines) < 10:
                return None

            candidates = [i for i in range(1, len(lines)) if
                          25 < lines[i]['time'] < (duration - 25) and len(lines[i]['text'].split()) >= 3]

            if not candidates:
                return None

            idx = random.choice(candidates)

            return {
                "start_time": max(0, lines[idx]['time'] - 20),
                "stop_time": lines[idx]['time'],
                "previous_line": lines[idx - 1]['text'],
                "hidden_answer": lines[idx]['text']
            }
        except Exception as e:
            print(f"  Erreur Deezer Lyrics : {e}")
            return None

    async def generate_last_word_challenge_jit(self, track_id: str, duration: int) -> Optional[Dict[str, Any]]:
        if not self.api_token:
            return None

        try:
            # 1. Récupération des paroles
            params = {"method": "song.getLyrics", "api_version": "1.0", "api_token": self.api_token}
            r = self.session.post("https://www.deezer.com/ajax/gw-light.php", params=params,
                                  json={"sng_id": str(track_id)}, timeout=5)
            data = r.json()

            if 'results' not in data or not data['results'].get('LYRICS_SYNC_JSON'):
                return None

            sync_data = data['results']['LYRICS_SYNC_JSON']

            lines = []
            for item in sync_data:
                line_text = item.get("line", "").strip()
                if line_text:
                    timestamp = int(item.get("milliseconds", 0)) / 1000.0
                    lines.append({"time": timestamp, "text": line_text})

            if len(lines) < 10:
                return None

            # 2. Le code choisit la ligne cible (pour garantir les timestamps)
            valid_indices = [i for i in range(1, len(lines)) if
                             25 < lines[i]['time'] < (duration - 15) and len(lines[i]['text'].split()) >= 3]
            if not valid_indices:
                return None

            idx = random.choice(valid_indices)
            target_line = lines[idx]

            # 3. NOUVEAU : On compile TOUTES les paroles pour le contexte global
            full_lyrics = "\n".join([l['text'] for l in lines])

            # 4. Prompt optimisé : Factuel, basé sur la cible, avec contexte complet
            prompt = f"""Tu rédiges une question pour un jeu de déduction musical.

    PAROLES COMPLÈTES (Pour comprendre le contexte global) :
    {full_lyrics}

    LA PHRASE À FAIRE DEVINER (CIBLE) :
    "{target_line['text']}"

    RÈGLES ABSOLUES :
    1. Pose UNE SEULE question factuelle, directe et très courte (max 15 mots).
    2. La question doit interroger sur "Que fait-il ?", "Où est-il ?", "Qui est-ce ?", "Que veut-il ?" en se basant EXCLUSIVEMENT sur l'action de la CIBLE.
    3. Ne mets AUCUN mot de la CIBLE dans ta question.
    4. N'invente pas d'histoire, reste terre-à-terre sur le sens de la phrase.
    5. Renvoie UNIQUEMENT la question brute, sans aucun préfixe ni guillemets.

    Exemple si la cible est "9.2 c'est l'élite" : Quel département est considéré comme le meilleur ?
    """

            # 5. Appel au modèle 70B (Très intelligent)
            chat_completion = await groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",  # LE MEILLEUR MODÈLE GRATUIT
                temperature=0.3,  # Température basse pour être factuel et précis
                max_tokens=40,  # Économie massive de tokens de sortie
                timeout=3.0
            )

            generated_question = chat_completion.choices[0].message.content.strip()

            start_timestamp = max(0.0, target_line['time'] - 20.0)

            return {
                "timestamp_start": start_timestamp,
                "target_time": target_line['time'],
                "question": generated_question,
                "expected_answer": target_line['text']
            }

        except Exception as e:
            print(f"  Erreur Last Word Challenge (JIT) : {e}")
            if 'target_line' in locals():
                # Le vrai fallback "Karaoké" en cas de crash réseau
                return {
                    "timestamp_start": max(0.0, target_line['time'] - 20.0),
                    "target_time": target_line['time'],
                    "question": f"Que chante l'artiste juste après : '{lines[idx - 1]['text']}' ?",
                    "expected_answer": target_line['text']
                }
            return None

    # --- 2. STREAMING ROBUSTE (V6 + FALLBACK ENCRYPTED) ---
    def get_full_track_url(self, track_id: str, is_retry: bool = False) -> Tuple[Optional[str], Optional[str], bool]:
        if not self.api_token or not self.license_token:
            return None, None, False

        try:
            r = self.session.post("https://www.deezer.com/ajax/gw-light.php",
                                  params={"method": "song.getData", "api_version": "1.0", "api_token": self.api_token},
                                  json={"sng_id": str(track_id)})
            track_info = r.json().get('results')
            if not track_info: return None, None, False

            sng_id = track_info.get("SNG_ID")
            track_token = track_info.get("TRACK_TOKEN")
            fallback_id = track_info.get("FALLBACK", {}).get("SNG_ID")
        except Exception as e:
            print(f"⚠️ Erreur Metadata: {e}")
            return None, None, False

        try:
            payload = {
                "license_token": self.license_token,
                "media": [{"type": "FULL", "formats": [{"cipher": "BF_CBC_STRIPE", "format": "MP3_128"},
                                                       {"cipher": "BF_CBC_STRIPE", "format": "MP3_64"}]}],
                "track_tokens": [track_token]
            }
            r = self.session.post("https://media.deezer.com/v1/get_url", json=payload, timeout=10)
            res = r.json()
            if 'data' in res and res['data'] and 'media' in res['data'][0]:
                url = res['data'][0]['media'][0]['sources'][0]['url']
                print(f"✅ URL FULL trouvée (V6) pour {track_id}")
                return url, sng_id, True
        except:
            print(f"⚠️ Méthode V6 échouée pour {track_id}")

        try:
            print(f"🔗 Tentative via Fallback Encrypted URL pour {track_id}...")
            url = self._get_encrypted_file_url(sng_id, track_info["MD5_ORIGIN"], track_info["MEDIA_VERSION"])
            requests.head(url, timeout=3)
            return url, sng_id, True
        except Exception as e:
            print(f"❌ Erreur Fallback URL: {e}")

            # D. TENTATIVE 3 : FALLBACK SNG_ID (Relance avec l'ID de secours)
            if fallback_id and not is_retry:
                print(f"🔄 Retentative avec l'ID de remplacement : {fallback_id}")
                return self.get_full_track_url(fallback_id, is_retry=True)

        return None, None, False

    def _get_encrypted_file_url(self, meta_id: str, track_hash: str, media_version: str):
        format_number = 1
        url_bytes = b"\xa4".join([
            track_hash.encode(),
            str(format_number).encode(),
            str(meta_id).encode(),
            str(media_version).encode()
        ])
        url_hash = hashlib.md5(url_bytes).hexdigest()
        info_bytes = bytearray(url_hash.encode()) + b"\xa4" + url_bytes + b"\xa4"

        padding_len = 16 - (len(info_bytes) % 16)
        info_bytes.extend(b"." * padding_len)

        path = binascii.hexlify(
            AES.new(AES_KEY_MOBILE, AES.MODE_ECB).encrypt(info_bytes)
        ).decode("utf-8")
        return f"https://e-cdns-proxy-{track_hash[0]}.dzcdn.net/mobile/1/{path}"

    def generate_blowfish_key(self, sng_id: str) -> bytes:
        id_md5 = hashlib.md5(str(sng_id).encode()).hexdigest()
        key = "".join(chr(ord(id_md5[i]) ^ ord(id_md5[i + 16]) ^ ord(BLOWFISH_SECRET[i])) for i in range(16))
        return key.encode('iso-8859-1')
