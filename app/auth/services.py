import hashlib
import json
import base64
from curl_cffi.requests import AsyncSession


async def get_arl_from_api(email: str, password: str) -> str:
    # 1. Décryptage des clés Saturne (447462 / a83bf7f...cf)
    client_id = base64.b64decode("NDQ3NDYy").decode('utf-8')
    client_secret = base64.b64decode("YTgzYmY3ZjM4YWQyZjEzN2U0NDQ3MjdjZmMzNzc1Y2Y=").decode('utf-8')

    # 2. Cryptographie MD5 conforme au script
    hashed_pwd = hashlib.md5(password.encode('utf-8')).hexdigest()
    raw_hash = f"{client_id}{email}{hashed_pwd}{client_secret}"
    hash_param = hashlib.md5(raw_hash.encode('utf-8')).hexdigest()

    # 3. Headers imitant parfaitement le script
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36",
        "X-User-IP": "1.1.1.1",
        "x-deezer-client-ip": "1.1.1.1",
        "Accept": "*/*",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Cache-Control": "max-age=0",
    }

    # On utilise curl_cffi pour simuler l'empreinte TLS d'un navigateur
    async with AsyncSession(impersonate="chrome110", headers=headers) as client:
        try:
            # --- ÉTAPE 1 : RÉCUPÉRER LES COOKIES INITIAUX (sid) ---
            # Le script fait un GET sur getUserData AVANT le login
            print("1. Initialisation des cookies (getUserData)...")
            init_url = "https://www.deezer.com/ajax/gw-light.php?method=deezer.getUserData&input=3&api_version=1.0&api_token=null"
            await client.get(init_url)

            # --- ÉTAPE 2 : OBTENIR LE TOKEN (Le login OAuth) ---
            # Le script utilise connect.deezer.com avec les paramètres dans l'URL (GET)
            print("2. Tentative de login (OAuth)...")
            auth_url = "https://connect.deezer.com/oauth/user_auth.php"
            params = {
                "app_id": client_id,
                "login": email,
                "password": hashed_pwd,
                "hash": hash_param
            }

            # On passe les cookies obtenus à l'étape 1
            res_auth = await client.get(auth_url, params=params)

            if res_auth.status_code != 200:
                print(f"❌ Erreur HTTP {res_auth.status_code}")
                return None

            try:
                auth_data = res_auth.json()
            except:
                print(f"❌ Réponse non JSON : {res_auth.text[:100]}")
                return None

            if "access_token" not in auth_data:
                print(f"❌ Échec Login : {auth_data}")
                return None

            print("✅ Token obtenu !")

            # --- ÉTAPE 3 : RÉCUPÉRATION DE L'ARL (Gateway) ---
            print("3. Extraction de l'ARL...")
            # Une fois loggé, les cookies du client contiennent la session authentifiée
            gw_url = "https://www.deezer.com/ajax/gw-light.php?method=user.getArl&input=3&api_version=1.0&api_token=null"
            res_gw = await client.get(gw_url)
            gw_data = res_gw.json()

            arl = gw_data.get("results")

            if arl:
                print(f"*** 🎉 VICTOIRE SATURNE ! ARL : {arl[:15]}... ***")
                return arl

            # Vérification ultime dans les cookies
            if 'arl' in client.cookies:
                return client.cookies['arl']

            print(f"❌ ARL non trouvé : {gw_data}")
            return None

        except Exception as e:
            print(f"--- ERREUR : {e} ---")
            return None
