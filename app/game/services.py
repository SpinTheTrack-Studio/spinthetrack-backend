import binascii
import hashlib
import random
from typing import Optional, Tuple, Dict, Any
import requests
import urllib3
from Crypto.Cipher import AES

# --- CONFIGURATION ---
BLOWFISH_SECRET = "g4el58wc0zvf9na1"
# Clé statique identifiée dans streamrip pour le fallback mobile
AES_KEY_MOBILE = b"jo6aey6haid2Teih"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cache-Control": "no-cache",
    "Referer": "https://www.deezer.com/"
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
            # Force l'input 3 pour avoir le license_token long
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
        Ultra stable, aucun rate-limit tiers, et correspond à 100% au fichier audio !
        """
        if not self.api_token:
            return None

        try:
            # Appel direct à l'API interne de Deezer
            params = {
                "method": "song.getLyrics",
                "api_version": "1.0",
                "api_token": self.api_token
            }
            # On demande les paroles via l'ID exact de la musique !
            r = self.session.post(
                "https://www.deezer.com/ajax/gw-light.php",
                params=params,
                json={"sng_id": str(track_id)},
                timeout=10
            )

            data = r.json()

            # Vérification de la présence des paroles synchronisées
            if 'results' not in data or not data['results'].get('LYRICS_SYNC_JSON'):
                print(f"⚠️ Pas de paroles synchronisées sur Deezer pour {track_id}")
                return None

            sync_data = data['results']['LYRICS_SYNC_JSON']

            # --- PARSING DU JSON DEEZER ---
            lines = []
            for item in sync_data:
                line_text = item.get("line", "").strip()
                # On ignore les lignes vides
                if line_text:
                    # Deezer donne le temps en millisecondes, on convertit en secondes
                    timestamp = int(item.get("milliseconds", 0)) / 1000.0
                    lines.append({"time": timestamp, "text": line_text})

            if len(lines) < 10:
                return None

            # --- LOGIQUE DE SÉLECTION DU CHALLENGE ---
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
            print(f"❌ Erreur Deezer Lyrics : {e}")
            return None

    # --- 2. STREAMING ROBUSTE (V6 + FALLBACK ENCRYPTED) ---
    def get_full_track_url(self, track_id: str, is_retry: bool = False) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Récupère l'URL.
        1. Tente la méthode V6 standard.
        2. En cas d'échec, tente l'URL cryptée AES (méthode streamrip).
        3. Si toujours échec, tente avec le SNG_ID de secours (FALLBACK).
        """
        if not self.api_token or not self.license_token:
            return None, None, False

        # A. Récupération des métadonnées (MD5, Version, Track Token)
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

        # B. TENTATIVE 1 : MÉTHODE V6 (Multi-formats)
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

        # C. TENTATIVE 2 : FALLBACK URL CRYPTÉE (AES / Mobile Proxy)
        try:
            print(f"🔗 Tentative via Fallback Encrypted URL pour {track_id}...")
            url = self._get_encrypted_file_url(sng_id, track_info["MD5_ORIGIN"], track_info["MEDIA_VERSION"])
            # On vérifie si l'URL répond
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
        """Génération d'URL mobile AES identifiée dans streamrip"""
        format_number = 1
        url_bytes = b"\xa4".join([
            track_hash.encode(),
            str(format_number).encode(),
            str(meta_id).encode(),
            str(media_version).encode()
        ])
        url_hash = hashlib.md5(url_bytes).hexdigest()
        info_bytes = bytearray(url_hash.encode()) + b"\xa4" + url_bytes + b"\xa4"

        # Padding AES ECB
        padding_len = 16 - (len(info_bytes) % 16)
        info_bytes.extend(b"." * padding_len)

        # Clé statique streamrip: jo6aey6haid2Teih
        path = binascii.hexlify(
            AES.new(AES_KEY_MOBILE, AES.MODE_ECB).encrypt(info_bytes)
        ).decode("utf-8")

        return f"https://e-cdns-proxy-{track_hash[0]}.dzcdn.net/mobile/1/{path}"

    def generate_blowfish_key(self, sng_id: str) -> bytes:
        id_md5 = hashlib.md5(str(sng_id).encode()).hexdigest()
        key = "".join(chr(ord(id_md5[i]) ^ ord(id_md5[i + 16]) ^ ord(BLOWFISH_SECRET[i])) for i in range(16))
        return key.encode('iso-8859-1')
