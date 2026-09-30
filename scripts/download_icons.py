"""Télécharge les icônes Albion dans assets/icons/<ID>.png (outil de dev, pas utilisé au runtime).

Le bot lit ces fichiers en local pour dessiner les images de builds/compos, sans dépendre
du CDN d'Albion (lent / instable depuis Railway). Le CDN reste un secours pour un objet absent.

Usage :
    python -m scripts.download_icons                       # catalogue du site par défaut
    python -m scripts.download_icons chemin/vers/items.json
    python -m scripts.download_icons --force               # re-télécharge tout

Le catalogue est le fichier items.json de lilium-site (liste de {"id", "icon", ...}) ;
il n'est lu qu'ici, le bot ne dépend pas du site pour fonctionner.
"""
import asyncio
import io
import json
import sys
from pathlib import Path

import aiohttp
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "assets" / "icons"
DEFAULT_CATALOG = ROOT.parent / "lilium-site" / "api" / "app" / "data" / "items.json"
URL = "https://render.albiononline.com/v1/item/{icon}.png?size=128"


def compress(data: bytes) -> bytes:
    """PNG 128 px, palette 256 couleurs + alpha : ~4× plus léger, invisible à cette taille."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    out = io.BytesIO()
    img.quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(out, format="PNG", optimize=True)
    return out.getvalue()


async def download(session, sem, item, force) -> str:
    target = ICONS_DIR / f"{item['id']}.png"
    if target.exists() and not force:
        return "skip"
    async with sem:
        for _ in range(3):
            try:
                async with session.get(URL.format(icon=item["icon"]), timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        return f"HTTP {resp.status}"
                    target.write_bytes(compress(await resp.read()))
                    return "ok"
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(1)
    return "échec"


async def main(argv: list[str]) -> int:
    force = "--force" in argv
    paths = [a for a in argv if not a.startswith("--")]
    catalog = Path(paths[0]) if paths else DEFAULT_CATALOG
    items = json.loads(catalog.read_text(encoding="utf-8"))
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(6)
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(download(session, sem, it, force) for it in items))
    failed = [(it["id"], r) for it, r in zip(items, results) if r not in ("ok", "skip")]
    print(f"{results.count('ok')} téléchargées, {results.count('skip')} déjà présentes, {len(failed)} en échec")
    for item_id, reason in failed:
        print(f"  ✗ {item_id} : {reason}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
