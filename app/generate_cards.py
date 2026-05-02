import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()


class DeezerCardGenerator:
    def __init__(self, arl):
        self.session = requests.Session()
        self.session.cookies.set('arl', arl, domain='.deezer.com')
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Cache-Control": "no-cache",
            "Origin": "https://www.deezer.com",
            "Referer": "https://www.deezer.com/"
        })
        self.api_token = None
        self._init_session()

        # Mapping des genres (IDs officiels Deezer + IDs observés)
        self.GENRE_MAPPING = {
            0: "Tous",
            2: "Afro / World",
            3: "Rap Alternatif",
            7: "Electro / House",
            10: "Variété Française",
            12: "Chanson Française",
            14: "Soul & Funk",
            16: "Musique Asiatique",
            19: "World Music",
            25: "Bande Originale (BO)",
            50: "Metal",
            71: "Latino",
            75: "Musique Brésilienne",
            81: "Musique Indienne",
            85: "Alternative",
            95: "Jeunesse",
            98: "Classique",
            106: "Electro",
            113: "Dance",
            116: "Rap/Hip Hop",
            129: "Reggae",
            132: "Pop",
            144: "Reggaeton",
            152: "Rock",
            153: "Blues",
            165: "R&B",
            169: "Soul",
            173: "Jazz",
            180: "Latino",
            186: "Techno",
            197: "Films/Jeux Vidéo",
            255: "Soundtrack",
            457: "Livres Audio",
            464: "Podcasts",
            466: "Sport",
            772: "J-Pop",
            1175: "K-Pop",
            2537: "Lo-Fi / Chill",
            6897: "Rap US",
            25481: "Trap",
            65535: "Divers"
        }

    def _init_session(self):
        print("🕵️  Initialisation session...")
        try:
            r = self.session.get("https://www.deezer.com/ajax/gw-light.php",
                                 params={"method": "deezer.getUserData", "api_version": "1.0", "api_token": "null"},
                                 timeout=10)
            data = r.json()
            if 'results' not in data:
                print("❌ ARL invalide.")
                sys.exit(1)
            self.api_token = data['results']['checkForm']
        except Exception as e:
            print(f"❌ Erreur session : {e}")
            sys.exit(1)

    def fetch_playlist_data(self, playlist_id):
        print(f"   📥 Scan playlist {playlist_id}...")
        try:
            # 1. Récupération des IDs via pagePlaylist (Méthode robuste)
            r = self.session.post("https://www.deezer.com/ajax/gw-light.php",
                                  params={"method": "deezer.pagePlaylist", "api_version": "1.0",
                                          "api_token": self.api_token},
                                  json={"playlist_id": str(playlist_id), "lang": "fr", "nb": -1, "start": 0}
                                  )
            data = r.json()

            if 'error' in data and data['error']:
                print(f"      ❌ Erreur API : {data['error']}")
                return None

            playlist_data = data.get('results', {})
            playlist_name = playlist_data.get('DATA', {}).get('TITLE', f"Playlist {playlist_id}")
            songs_list = playlist_data.get('SONGS', {}).get('data', [])

            # On récupère les SNG_ID
            sng_ids = [str(s['SNG_ID']) for s in songs_list if 'SNG_ID' in s]

            if not sng_ids:
                print("      ⚠️ Playlist vide.")
                return None

        except Exception as e:
            print(f"      ❌ Erreur scan : {e}")
            return None

        # 2. Enrichissement via song.getListData
        print(f"   📡 Traitement de {len(sng_ids)} titres...")
        playlist_cards = {}
        chunk_size = 50

        for i in range(0, len(sng_ids), chunk_size):
            chunk = sng_ids[i:i + chunk_size]
            try:
                r_rich = self.session.post("https://www.deezer.com/ajax/gw-light.php",
                                           params={"method": "song.getListData", "api_version": "1.0",
                                                   "api_token": self.api_token},
                                           json={"sng_ids": chunk}
                                           )
                rich_results = r_rich.json().get('results', {}).get('data', [])

                for t in rich_results:
                    # Génération ID carte unique
                    card_id = f"card_{playlist_id}_{len(playlist_cards)}"

                    # --- TAGS ---
                    tags = []

                    # Année
                    date_str = t.get('PHYSICAL_RELEASE_DATE') or t.get('DIGITAL_RELEASE_DATE')
                    year = "Inconnu"
                    if date_str and isinstance(date_str, str):
                        try:
                            year_int = int(date_str.split('-')[0])
                            year = str(year_int)
                            tags.append(year)
                            if year_int >= 2020:
                                tags.append("2020s")
                            elif year_int >= 2010:
                                tags.append("2010s")
                            elif year_int >= 2000:
                                tags.append("2000s")
                            elif year_int >= 1990:
                                tags.append("90s")
                            elif year_int >= 1980:
                                tags.append("80s")
                            else:
                                tags.append("Oldies")
                        except:
                            pass

                    # Genre
                    genre_id = int(t.get('GENRE_ID', 0) or t.get('ALB_GENRE_ID', 0))
                    if genre_id in self.GENRE_MAPPING:
                        tags.append(self.GENRE_MAPPING[genre_id])

                    # Hit
                    rank = int(t.get('RANK_SNG', 0) or t.get('RANK', 0))
                    if rank > 600000: tags.append("Hit 🔥")

                    # Explicit
                    if str(t.get('EXPLICIT_LYRICS', '0')) == '1': tags.append("Explicit 🤬")

                    # Cover HD
                    pic_hash = t.get('ALB_PICTURE', '')
                    cover_url = f"https://e-cdns-images.dzcdn.net/images/cover/{pic_hash}/500x500-000000-80-0-0.jpg" if pic_hash else ""

                    # --- OBJET FINAL ALLÉGÉ AVEC PLAYLIST_ID ---
                    playlist_cards[card_id] = {
                        "id": str(t['SNG_ID']),  # ID Track
                        "playlist_id": str(playlist_id),  # <--- AJOUTÉ ICI
                        "title": t['SNG_TITLE'],
                        "artist": t['ART_NAME'],
                        "cover": cover_url,
                        "tags": tags,
                        "year": year
                    }

            except Exception as e:
                print(f"      ⚠️ Erreur batch : {e}")
                continue

        print(f"      ✅ {len(playlist_cards)} cartes.")
        return playlist_name, playlist_cards


def main():
    print("=== DEEZER CARD GENERATOR (VERSION ROBUSTE) ===")

    # 1. Saisie ARL
    arl = os.environ.get("ARL")
    if not arl:
        print("ARL vide, abandon.")
        return

    # 2. Saisie Playlists
    print("\nEntrez les IDs des playlists (séparés par des virgules)")
    print("Exemple: 123456789, 987654321")
    pl_input = "12232544271, 12232540071, 713806955, 6153956244, 13390026243, 3809722162, 14136311941, 9456952822, 3631248842, 4543271164"
    if not pl_input: return
    playlist_ids = [pid.strip() for pid in pl_input.split(',') if pid.strip()]

    generator = DeezerCardGenerator(arl)
    global_library = {}

    for pid in playlist_ids:
        res = generator.fetch_playlist_data(pid)
        if res:
            name, cards = res
            if name in global_library: name = f"{name} ({pid})"
            global_library[name] = cards
            time.sleep(0.2)

    with open("data/cards.json", "w", encoding="utf-8") as f:
        json.dump(global_library, f, indent=4, ensure_ascii=False)
    print("\n✨ Terminé. 'cards.json' mis à jour.")


if __name__ == "__main__":
    main()
