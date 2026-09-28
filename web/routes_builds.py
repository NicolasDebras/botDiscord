import discord
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import db
from config import ROLES
from web import auth

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _bot(request: Request) -> discord.Client:
    return request.app.state.bot


@router.get("/g/{guild_id}/builds", response_class=HTMLResponse)
async def list_builds(request: Request, guild_id: int, role: str = "", type_acti: str = ""):
    user   = await auth.require_membership(request, _bot(request), guild_id)
    staff  = await auth.is_staff(_bot(request), guild_id, int(user["id"]))
    builds = await db.get_builds(guild_id, role=role or None, type_acti=type_acti or None)
    return _templates(request).TemplateResponse(request, "builds/list.html", {
        "user": user, "guild_id": guild_id, "builds": builds, "staff": staff,
        "roles": sorted(ROLES.keys()), "role_filter": role, "type_filter": type_acti,
    })


@router.get("/g/{guild_id}/builds/new", response_class=HTMLResponse)
async def new_build_form(request: Request, guild_id: int):
    user = await auth.require_staff(request, _bot(request), guild_id)
    return _templates(request).TemplateResponse(request, "builds/form.html", {
        "user": user, "guild_id": guild_id, "roles": sorted(ROLES.keys()), "build": None,
    })


@router.post("/g/{guild_id}/builds/new")
async def create_build(
    request: Request, guild_id: int,
    name: str = Form(...), role: str = Form(...), type_acti: str = Form("PVP"),
    weapon: str = Form(""), notes: str = Form(""), image: str = Form(""),
):
    user = await auth.require_staff(request, _bot(request), guild_id)
    await db.add_build(
        guild_id, name.strip(), role.strip().upper(), type_acti, weapon.strip(), notes.strip(), image.strip(),
        user["id"], user["username"],
    )
    return RedirectResponse(f"/g/{guild_id}/builds", status_code=303)


@router.get("/g/{guild_id}/builds/{build_id}/edit", response_class=HTMLResponse)
async def edit_build_form(request: Request, guild_id: int, build_id: int):
    user  = await auth.require_staff(request, _bot(request), guild_id)
    build = await db.get_build_by_id(build_id, guild_id)
    if not build:
        return RedirectResponse(f"/g/{guild_id}/builds", status_code=303)
    return _templates(request).TemplateResponse(request, "builds/form.html", {
        "user": user, "guild_id": guild_id, "roles": sorted(ROLES.keys()), "build": build,
    })


@router.post("/g/{guild_id}/builds/{build_id}/edit")
async def update_build(
    request: Request, guild_id: int, build_id: int,
    name: str = Form(...), role: str = Form(...), type_acti: str = Form("PVP"),
    weapon: str = Form(""), notes: str = Form(""), image: str = Form(""),
):
    await auth.require_staff(request, _bot(request), guild_id)
    await db.update_build(
        build_id, guild_id, name.strip(), role.strip().upper(), type_acti, weapon.strip(), notes.strip(), image.strip(),
    )
    return RedirectResponse(f"/g/{guild_id}/builds", status_code=303)


@router.post("/g/{guild_id}/builds/{build_id}/delete")
async def delete_build(request: Request, guild_id: int, build_id: int):
    await auth.require_staff(request, _bot(request), guild_id)
    await db.delete_build(build_id, guild_id)
    return RedirectResponse(f"/g/{guild_id}/builds", status_code=303)
