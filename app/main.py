import asyncio
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth import login
from app.game import routes

# Correction impérative pour Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="SpinTheTrack API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login.router, prefix="/api")
app.include_router(routes.router, prefix="/api")

# Lancement programmatique pour éviter le conflit loop_factory
if __name__ == "__main__":
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=8000, reload=False)
    server = uvicorn.Server(config)
    # On utilise une méthode de lancement plus directe
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.serve())
