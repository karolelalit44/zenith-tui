"""Switch active provider to openrouter with a specific model."""
import asyncio
import sys
import os
sys.path.insert(0, r"D:\vdo\code\zenith-frontend-tui")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for line in open(r"D:\vdo\code\zenith-frontend-tui\.keys").readlines():
    if "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from db.connection import Database, resolve_db_path

async def fix():
    db = Database(resolve_db_path())
    await db.connect()

    or_key = os.environ.get("openrouter_api", "")
    await db.execute("UPDATE providers SET is_active = 0")
    await db.execute("UPDATE providers SET is_active = 1 WHERE id = 'openrouter'")
    await db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('active_provider', 'openrouter')")
    await db.execute("UPDATE providers SET model = ?, api_key = ? WHERE id = 'openrouter'",
                     ("cohere/north-mini-code:free", or_key))
    await db.commit()

    row = await db.fetch_one("SELECT value FROM app_settings WHERE key = 'active_provider'")
    print(f"Active: {row}")
    prov = await db.fetch_one("SELECT id, model, api_key FROM providers WHERE id = 'openrouter'")
    print(f"OpenRouter: model={prov['model']}, has_key={bool(prov['api_key'])}")
    await db.close()

asyncio.run(fix())
