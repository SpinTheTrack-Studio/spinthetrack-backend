import asyncio
import random
from playwright.async_api import async_playwright


async def get_arl_with_playwright(email, password):
    async with async_playwright() as p:
        # Lancement du navigateur
        browser = await p.chromium.launch(
            headless=True,  # Toujours True en Docker
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",  # Demande à Chrome d'utiliser /tmp au lieu de /dev/shm
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        # --- 1. STEALTH NATIF ---
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            print("1. Navigation vers Deezer...")
            await page.goto("https://www.deezer.com/fr/login", wait_until="domcontentloaded", timeout=60000)

            # --- 2. GESTION BANNIÈRE COOKIES ---
            print("2. Gestion Bannière...")
            await asyncio.sleep(2)  # Pause importante demandée

            try:
                # On cherche le bouton "Accepter"
                cookie_btn = page.locator("#gdpr-btn-accept-all")
                if await cookie_btn.is_visible(timeout=3000):
                    print("   -> Clic sur Accepter les cookies.")
                    await cookie_btn.click()
                    # On laisse le temps à la bannière de disparaître pour ne pas gêner le clic suivant
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"   -> Pas de bannière ou erreur: {e}")

            # --- 3. REMPLISSAGE FORMULAIRE ---
            print("3. Remplissage (Mode Humain)...")
            # On utilise tes sélecteurs validés
            await page.wait_for_selector("input#email", state="visible")

            # Frappe lente
            await page.type("input#email", email, delay=random.randint(50, 150))
            await asyncio.sleep(0.5)
            await page.type("input#password", password, delay=random.randint(50, 150))

            await asyncio.sleep(1)

            print("4. Validation...")
            # Clic via data-testid
            await page.get_by_test_id("login-button").click()

            # --- 4. ATTENTE DE RÉUSSITE ---
            print("5. Attente de la connexion...")
            print(">>> Vérification du Captcha en cours (30 sec max)... <<<")

            try:
                # On met un timeout de 30 secondes (30000 ms) au lieu de 0
                await page.wait_for_function(
                    "() => !window.location.href.includes('login') && !window.location.href.includes('account')",
                    timeout=30000
                )
                print("✅ URL changée ! Nous avons quitté la page de login.")

            except Exception as e:
                # Si le délai est dépassé, on prend une photo !
                print("❌ Délai dépassé ou bloqué par Deezer !")
                screenshot_path = "/app/data/sessions/debug_deezer.png"
                await page.screenshot(path=screenshot_path)
                print(f"📸 Capture d'écran de l'erreur sauvegardée ici : {screenshot_path}")
                return None

            # --- 5. EXTRACTION DU COOKIE PAR PYTHON ---
            # Python a accès aux cookies HttpOnly via context.cookies()
            # On attend un tout petit peu que le navigateur stocke bien tout
            await asyncio.sleep(2)

            all_cookies = await context.cookies()
            arl_cookie = next((c['value'] for c in all_cookies if c['name'] == 'arl'), None)

            if arl_cookie:
                print(f"*** SUCCÈS ! ARL RÉCUPÉRÉ : {arl_cookie[:15]}... ***")
                return arl_cookie
            else:
                print("❌ ÉCHEC : URL changée mais pas de cookie 'arl' trouvé par Python.")
                return None

        except Exception as e:
            print(f"--- ERREUR : {e} ---")
            return None

        finally:
            # On ferme le navigateur une fois fini
            await browser.close()
