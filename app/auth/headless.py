import hashlib

import httpx  # Plus rapide et asynchrone, idéal pour FastAPI


async def get_arl_from_api(email: str, password: str) -> str:
    # 1. Les clés secrètes extraites de Deemix/Refreezer
    client_id = "172365"
    client_secret = "fb0bec7ccc063dab0417eb7b0d847f34"

    # 2. Le hachage cryptographique
    hashed_pwd = hashlib.md5(password.encode('utf-8')).hexdigest()
    raw_hash = f"{client_id}{email}{hashed_pwd}{client_secret}"
    hash_param = hashlib.md5(raw_hash.encode('utf-8')).hexdigest()

    # On utilise un client HTTP qui garde les cookies en mémoire (CookieJar)
    async with httpx.AsyncClient(headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36"}) as client:

        # 3. Obtenir le Access Token
        auth_url = "https://api.deezer.com/auth/token"
        params = {
            "app_id": client_id,
            "login": email,
            "password": hashed_pwd,
            "hash": hash_param
        }

        try:
            auth_res = await client.get(auth_url, params=params)
            auth_data = auth_res.json()
            access_token = auth_data.get("access_token")

            if not access_token:
                print(f"❌ Échec de l'authentification API : {auth_data}")
                return None

            print("✅ Token obtenu, initialisation de la session...")

            # 4. Initialiser la session en simulant une action (comme le fait Deemix)
            # Cette étape est cruciale pour que Deezer nous donne un cookie de session (sid)
            track_url = "https://api.deezer.com/platform/generic/track/3135556"
            await client.get(track_url, headers={"Authorization": f"Bearer {access_token}"})

            # 5. Interroger la Gateway pour obtenir l'ARL
            gw_url = "https://www.deezer.com/ajax/gw-light.php?method=user.getArl&input=3&api_version=1.0&api_token=null"
            gw_res = await client.get(gw_url)
            gw_data = gw_res.json()

            arl = gw_data.get("results")

            if arl:
                print(f"*** SUCCÈS ! ARL RÉCUPÉRÉ VIA API : {arl[:15]}... ***")
                return arl
            else:
                print("❌ Impossible d'extraire l'ARL de la Gateway.")
                return None

        except Exception as e:
            print(f"--- ERREUR API : {e} ---")
            return None
