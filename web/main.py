"""
web/main.py — Site web (builds & compos), lancé dans le même process que le
bot Discord (voir bot.py). Auth Discord OAuth2, permissions basées sur le
rôle staff configuré via /config → 🌐 Rôle staff du site web.
"""
import pathlib

import discord
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web import auth
from web.routes_builds import router as builds_router
from web.routes_compos import router as compos_router

_BASE_DIR = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def create_app(bot: discord.Client) -> FastAPI:
    app = FastAPI(title="LiliumBot — Builds & Compos")
    app.state.bot = bot
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")
    app.include_router(builds_router)
    app.include_router(compos_router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        user = auth.read_session(request)
        if user:
            return RedirectResponse("/guilds")
        return templates.TemplateResponse(request, "login.html", {})

    @app.get("/auth/login")
    async def login():
        return RedirectResponse(auth.build_authorize_url())

    @app.get("/auth/callback")
    async def callback(code: str | None = None, error: str | None = None):
        if error or not code:
            return RedirectResponse("/?error=1")
        access_token = await auth.exchange_code(code)
        user         = await auth.fetch_discord_user(access_token)
        response     = RedirectResponse("/guilds")
        auth.set_session_cookie(response, user)
        return response

    @app.get("/auth/logout")
    async def logout():
        response = RedirectResponse("/")
        auth.clear_session_cookie(response)
        return response

    @app.get("/guilds", response_class=HTMLResponse)
    async def guilds_list(request: Request):
        user = auth.require_login(request)
        guilds = auth.shared_guilds(bot, int(user["id"]))
        return templates.TemplateResponse(request, "guilds.html", {"user": user, "guilds": guilds})

    return app
