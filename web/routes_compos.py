import discord
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import db
from config import ROLES, DEFAULT_TEMPLATES
from web import auth

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _bot(request: Request) -> discord.Client:
    return request.app.state.bot


def _default_templates_for(guild_id: int) -> dict[str, dict]:
    return {
        name: tpl for name, tpl in DEFAULT_TEMPLATES.items()
        if not tpl.get("guild_ids") or guild_id in tpl["guild_ids"]
    }


async def _refresh_bot_cache() -> None:
    """Les compos écrites depuis le site doivent être utilisables immédiatement
    par /acti sans redémarrer le bot — même process, on recharge le cache."""
    from Service.activites import refresh_templates_cache
    await refresh_templates_cache()


def _build_template_entry(form) -> dict:
    roles   = form.getlist("role")
    counts  = form.getlist("count")
    weapons = form.getlist("weapon")
    pf_1    = {}
    weapon  = {}
    for r, c, w in zip(roles, counts, weapons):
        r = r.strip().upper()
        if not r or not c.strip():
            continue
        try:
            pf_1[r] = int(c)
        except ValueError:
            continue
        if w.strip():
            weapon[r] = w.strip()

    roles2   = form.getlist("role_pf2")
    counts2  = form.getlist("count_pf2")
    weapons2 = form.getlist("weapon_pf2")
    pf_2       = {}
    weapon_pf2 = {}
    for r, c, w in zip(roles2, counts2, weapons2):
        r = r.strip().upper()
        if not r or not c.strip():
            continue
        try:
            pf_2[r] = int(c)
        except ValueError:
            continue
        if w.strip():
            weapon_pf2[r] = w.strip()

    entry = {
        "description": form.get("description", "").strip(),
        "type_acti":   form.get("type_acti", "PVP"),
        "image":       form.get("image", "").strip(),
        "pf_1":        pf_1,
        "weapon":      weapon,
    }
    if pf_2:
        entry["pf_2"]       = pf_2
        entry["weapon_pf2"] = weapon_pf2
    return entry


@router.get("/g/{guild_id}/compos", response_class=HTMLResponse)
async def list_compos(request: Request, guild_id: int):
    user      = await auth.require_membership(request, _bot(request), guild_id)
    staff     = await auth.is_staff(_bot(request), guild_id, int(user["id"]))
    all_custom = await db.get_custom_templates()
    custom     = all_custom.get(guild_id, {})
    defaults   = _default_templates_for(guild_id)
    return _templates(request).TemplateResponse(request, "compos/list.html", {
        "user": user, "guild_id": guild_id, "staff": staff,
        "custom": custom, "defaults": defaults,
    })


@router.get("/g/{guild_id}/compos/new", response_class=HTMLResponse)
async def new_compo_form(request: Request, guild_id: int):
    user = await auth.require_staff(request, _bot(request), guild_id)
    builds = await db.get_builds(guild_id)
    return _templates(request).TemplateResponse(request, "compos/form.html", {
        "user": user, "guild_id": guild_id, "roles": sorted(ROLES.keys()),
        "builds": builds, "compo": None, "name": "",
    })


@router.post("/g/{guild_id}/compos/new")
async def create_compo(request: Request, guild_id: int):
    user = await auth.require_staff(request, _bot(request), guild_id)
    form = await request.form()
    name = form.get("name", "").strip()
    if not name:
        return RedirectResponse(f"/g/{guild_id}/compos/new", status_code=303)
    if name in DEFAULT_TEMPLATES:
        return _templates(request).TemplateResponse(request, "compos/form.html", {
            "user": user, "guild_id": guild_id, "roles": sorted(ROLES.keys()),
            "builds": await db.get_builds(guild_id), "compo": None, "name": name,
            "error": f"« {name} » est un template par défaut, choisis un autre nom.",
        }, status_code=400)

    entry = _build_template_entry(form)
    await db.save_custom_template(name, entry, guild_id=guild_id)
    await _refresh_bot_cache()
    return RedirectResponse(f"/g/{guild_id}/compos", status_code=303)


@router.get("/g/{guild_id}/compos/{name}/edit", response_class=HTMLResponse)
async def edit_compo_form(request: Request, guild_id: int, name: str):
    user       = await auth.require_staff(request, _bot(request), guild_id)
    all_custom = await db.get_custom_templates()
    compo      = all_custom.get(guild_id, {}).get(name)
    if not compo:
        return RedirectResponse(f"/g/{guild_id}/compos", status_code=303)
    builds = await db.get_builds(guild_id)
    return _templates(request).TemplateResponse(request, "compos/form.html", {
        "user": user, "guild_id": guild_id, "roles": sorted(ROLES.keys()),
        "builds": builds, "compo": compo, "name": name,
    })


@router.post("/g/{guild_id}/compos/{name}/edit")
async def update_compo(request: Request, guild_id: int, name: str):
    await auth.require_staff(request, _bot(request), guild_id)
    form  = await request.form()
    entry = _build_template_entry(form)
    await db.save_custom_template(name, entry, guild_id=guild_id)
    await _refresh_bot_cache()
    return RedirectResponse(f"/g/{guild_id}/compos", status_code=303)


@router.post("/g/{guild_id}/compos/{name}/delete")
async def delete_compo(request: Request, guild_id: int, name: str):
    await auth.require_staff(request, _bot(request), guild_id)
    await db.delete_custom_template(name, guild_id=guild_id)
    await _refresh_bot_cache()
    return RedirectResponse(f"/g/{guild_id}/compos", status_code=303)
