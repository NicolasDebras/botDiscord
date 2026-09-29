"""
web/dev_preview.py — Prévisualisation locale du site avec des données factices.

Ne touche à AUCUNE vraie donnée : pas de connexion Discord, pas de base
PostgreSQL, pas d'auth OAuth2 réelle. Sert uniquement à voir le rendu des
pages dans un navigateur. Les boutons "Enregistrer"/"Supprimer" ne
persistent rien, ils reviennent juste sur la liste.

Lancement :
    pip install fastapi "uvicorn[standard]" jinja2 python-multipart
    python -m web.dev_preview
    → http://localhost:8080
"""
import pathlib
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_BASE_DIR = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app = FastAPI(title="LiliumBot — Preview")
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

FAKE_USER = {
    "id": "123456789012345678",
    "username": "TestUser",
    "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
}
FAKE_GUILD_ID = 1
FAKE_GUILDS = [
    SimpleNamespace(id=1, name="Guilde de test", icon=None),
    SimpleNamespace(id=2, name="Autre serveur", icon=None),
]
FAKE_BUILDS = [
    {"id": 1, "name": "Tank 1H Masse", "role": "TANK", "type_acti": "PVP",
     "weapon": "1H Masse controle", "notes": "Contrôle principal, initie le combo.",
     "created_by_name": "TestUser", "image": ""},
    {"id": 2, "name": "Heal Sancti", "role": "HEAL", "type_acti": "PVP",
     "weapon": "Sancti Plaque", "notes": "Heal principal en plaque.",
     "created_by_name": "TestUser", "image": ""},
    {"id": 3, "name": "DPS Arc Long", "role": "DPS", "type_acti": "PVE",
     "weapon": "Arc Long", "notes": "", "created_by_name": "TestUser", "image": ""},
]
FAKE_CUSTOM_COMPOS = {
    "ZvZ Test": {
        "description": "Compo de démo pour la preview.",
        "type_acti": "PVP",
        "image": "",
        "pf_1": {"TANK": 2, "HEAL": 2, "DPS": 6},
        "weapon": {"TANK": "1H Masse controle", "HEAL": "Sancti Plaque"},
        "pf_2": {"TANK": 1, "DPS": 4},
        "weapon_pf2": {"TANK": "Second Repack"},
    },
}
FAKE_DEFAULT_COMPOS = {
    "Donjon Groupe 5": {
        "type_acti": "PVE", "image": "",
        "pf_1": {"TANK": 1, "DPS": 3, "HEAL": 1},
    },
}
FAKE_ROLES = ["TANK", "HEAL", "DPS", "SUPPORT", "CALLER", "SCOUT"]


def _ctx(request: Request, **extra) -> dict:
    return {"user": FAKE_USER, "guild_id": FAKE_GUILD_ID, **extra}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse("/guilds")


@app.get("/guilds", response_class=HTMLResponse)
async def guilds(request: Request):
    return templates.TemplateResponse(request, "guilds.html", {"user": FAKE_USER, "guild_id": None, "guilds": FAKE_GUILDS})


@app.get("/g/{guild_id}/builds", response_class=HTMLResponse)
async def builds_list(request: Request, guild_id: int, role: str = "", type_acti: str = ""):
    builds = FAKE_BUILDS
    if role:
        builds = [b for b in builds if b["role"] == role]
    if type_acti:
        builds = [b for b in builds if b["type_acti"] == type_acti]
    return templates.TemplateResponse(request, "builds/list.html", _ctx(
        request, builds=builds, staff=True, roles=FAKE_ROLES, role_filter=role, type_filter=type_acti,
    ))


@app.get("/g/{guild_id}/builds/new", response_class=HTMLResponse)
async def build_new(request: Request, guild_id: int):
    return templates.TemplateResponse(request, "builds/form.html", _ctx(request, roles=FAKE_ROLES, build=None))


@app.get("/g/{guild_id}/builds/{build_id}/edit", response_class=HTMLResponse)
async def build_edit(request: Request, guild_id: int, build_id: int):
    build = next((b for b in FAKE_BUILDS if b["id"] == build_id), FAKE_BUILDS[0])
    return templates.TemplateResponse(request, "builds/form.html", _ctx(request, roles=FAKE_ROLES, build=build))


@app.post("/g/{guild_id}/builds/new")
@app.post("/g/{guild_id}/builds/{build_id}/edit")
@app.post("/g/{guild_id}/builds/{build_id}/delete")
async def builds_noop(guild_id: int, build_id: int = 0):
    return RedirectResponse(f"/g/{guild_id}/builds", status_code=303)


@app.get("/g/{guild_id}/compos", response_class=HTMLResponse)
async def compos_list(request: Request, guild_id: int):
    return templates.TemplateResponse(request, "compos/list.html", _ctx(
        request, staff=True, custom=FAKE_CUSTOM_COMPOS, defaults=FAKE_DEFAULT_COMPOS,
    ))


@app.get("/g/{guild_id}/compos/new", response_class=HTMLResponse)
async def compo_new(request: Request, guild_id: int):
    return templates.TemplateResponse(request, "compos/form.html", _ctx(
        request, roles=FAKE_ROLES, builds=FAKE_BUILDS, compo=None, name="",
    ))


@app.get("/g/{guild_id}/compos/{name}/edit", response_class=HTMLResponse)
async def compo_edit(request: Request, guild_id: int, name: str):
    compo = FAKE_CUSTOM_COMPOS.get(name, next(iter(FAKE_CUSTOM_COMPOS.values())))
    return templates.TemplateResponse(request, "compos/form.html", _ctx(
        request, roles=FAKE_ROLES, builds=FAKE_BUILDS, compo=compo, name=name,
    ))


@app.post("/g/{guild_id}/compos/new")
@app.post("/g/{guild_id}/compos/{name}/edit")
@app.post("/g/{guild_id}/compos/{name}/delete")
async def compos_noop(guild_id: int, name: str = ""):
    return RedirectResponse(f"/g/{guild_id}/compos", status_code=303)


if __name__ == "__main__":
    print("👉 Preview sans données réelles : http://localhost:8080/guilds")
    uvicorn.run(app, host="0.0.0.0", port=8080)
