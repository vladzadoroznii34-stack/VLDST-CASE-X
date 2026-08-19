import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from secrets import SystemRandom
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .db import engine, get_db
from .game_data import CASES, RARITY_CHANCES
from .security import validate_telegram_init_data

log = logging.getLogger("vldst")
rng = SystemRandom()

app = FastAPI(title="VLDST CASE X", version="10.1.0")
app.mount("/static", StaticFiles(directory="frontend/public"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def bootstrap_database():
    """Create/migrate the schema and seed the VLDST catalog on every deploy/start.

    The seed uses ON CONFLICT DO NOTHING, so existing users, inventory and
    transactions are preserved while missing catalog rows are restored.
    """
    if not settings.database_url or not engine:
        log.warning("DATABASE_URL is not configured; database bootstrap skipped")
        return

    from pathlib import Path
    import psycopg

    root = Path(__file__).resolve().parents[2]
    schema_sql = (root / "database" / "schema.sql").read_text(encoding="utf-8")
    seed_sql = (root / "database" / "seed.sql").read_text(encoding="utf-8")
    url = settings.database_url.replace("postgres://", "postgresql://", 1)
    url = url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(schema_sql)
        conn.execute(seed_sql)
        cases_count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        items_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        if cases_count < len(CASES) or items_count < sum(len(c["items"]) for c in CASES):
            raise RuntimeError(
                f"Catalog bootstrap incomplete: cases={cases_count}, items={items_count}"
            )
    log.info("Database bootstrap complete: %s cases / %s items", cases_count, items_count)


@app.on_event("startup")
async def startup_bootstrap():
    # Never block Uvicorn/Render while PostgreSQL is bootstrapped.
    try:
        await asyncio.to_thread(bootstrap_database)
    except Exception:
        log.exception("Database bootstrap failed during startup")


ASSET_BASE = "/static/assets"
def item_asset(item_code: str) -> str:
    return f"{ASSET_BASE}/items/{item_code}.png"
def case_asset(case_code: str) -> str:
    return f"{ASSET_BASE}/cases/{case_code}.png"
def enrich_item(item: dict) -> dict:
    out = dict(item)
    out.setdefault("image_url", item_asset(str(out.get("item_code", ""))))
    return out
def enrich_case(case: dict) -> dict:
    out = dict(case)
    out["image_url"] = case_asset(str(out.get("case_code", "")))
    out["items"] = [enrich_item(i) for i in out.get("items", [])]
    return out

MISSION_CATALOG = [
    {"id": "open1", "title": "Открыть 1 кейс", "target": 1, "kind": "opens", "reward": 100},
    {"id": "open3", "title": "Открыть 3 кейса", "target": 3, "kind": "opens", "reward": 300},
    {"id": "new", "title": "Получить новый предмет", "target": 1, "kind": "items", "reward": 250},
    {"id": "sell", "title": "Продать предмет", "target": 1, "kind": "sales", "reward": 100},
]
ACHIEVEMENT_CATALOG = [
    {"id": "first", "title": "FIRST CASE", "target": 1, "kind": "opens", "reward": 500},
    {"id": "collector", "title": "Collector", "target": 20, "kind": "unique", "reward": 2000},
    {"id": "mythic", "title": "Mythic Hunter", "target": 1, "kind": "mythic", "reward": 10000},
    {"id": "master", "title": "Master", "target": 50, "kind": "opens", "reward": 50000},
]
SHOP_PRODUCTS = [
    {"id": "coins_50000", "title": "50K Coins", "stars": 25, "description": "50 000 игровых монет"},
    {"id": "coins_150000", "title": "150K Coins", "stars": 60, "description": "150 000 игровых монет"},
    {"id": "coins_500000", "title": "500K Coins", "stars": 150, "description": "500 000 игровых монет"},
    {"id": "premium", "title": "Premium", "stars": 100, "description": "Premium доступ к сезону"},
    {"id": "xp_boost", "title": "XP Boost", "stars": 50, "description": "x2 XP на 24 часа"},
    {"id": "season_pass", "title": "Season Pass", "stars": 100, "description": "Premium Season Pass"},
]
SEASON_REWARDS = [{"level": n, "free": 100 + n * 10, "premium": 250 + n * 25} for n in range(1, 51)]


def json_error(message: str, status: int):
    return JSONResponse(status_code=status, content={"ok": False, "detail": message})


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return json_error(str(exc.detail), exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    log.exception("Unhandled API error", exc_info=exc)
    return json_error("Internal server error", 500)


def tg(raw: str):
    try:
        return json.loads(validate_telegram_init_data(raw)["user"])
    except Exception as exc:
        raise HTTPException(401, str(exc))


def ensure_user(db: Session, telegram_user: dict):
    u = db.execute(
        text("SELECT * FROM users WHERE telegram_id=:id"),
        {"id": telegram_user["id"]},
    ).mappings().first()
    if u:
        return u
    db.execute(
        text(
            "INSERT INTO users(telegram_id,username,first_name,coins,xp,level) "
            "VALUES(:id,:u,:f,5000,0,1)"
        ),
        {
            "id": telegram_user["id"],
            "u": telegram_user.get("username", ""),
            "f": telegram_user.get("first_name", ""),
        },
    )
    db.commit()
    return db.execute(
        text("SELECT * FROM users WHERE telegram_id=:id"),
        {"id": telegram_user["id"]},
    ).mappings().first()


def current_user(db: Session, raw: str):
    user = ensure_user(db, tg(raw))
    if bool(user.get("blocked", False)):
        raise HTTPException(403, "Аккаунт заблокирован")
    return user


def catalog_case(code: str):
    return next((x for x in CASES if x["case_code"] == code), None)


def xp_level(xp: int) -> int:
    return max(1, 1 + int(xp // 100))


def progress_stats(db: Session, user_id: int):
    opens = db.execute(
        text("SELECT COUNT(*) FROM case_openings WHERE user_id=:u"),
        {"u": user_id},
    ).scalar_one()
    unique_items = db.execute(
        text("SELECT COUNT(*) FROM inventory WHERE user_id=:u AND quantity>0"),
        {"u": user_id},
    ).scalar_one()
    total_items = db.execute(
        text("SELECT COALESCE(SUM(quantity),0) FROM inventory WHERE user_id=:u"),
        {"u": user_id},
    ).scalar_one()
    sales = db.execute(
        text(
            "SELECT COUNT(*) FROM economy_transactions "
            "WHERE user_id=:u AND kind='ITEM_SELL'"
        ),
        {"u": user_id},
    ).scalar_one()
    mythic = db.execute(
        text(
            "SELECT COUNT(*) FROM inventory i JOIN items it ON it.item_code=i.item_code "
            "WHERE i.user_id=:u AND i.quantity>0 AND it.rarity='MYTHIC'"
        ),
        {"u": user_id},
    ).scalar_one()
    return {
        "opens": int(opens),
        "unique": int(unique_items),
        "total_items": int(total_items),
        "sales": int(sales),
        "mythic": int(mythic),
    }


def mission_progress(stats, mission):
    return min(stats.get(mission["kind"], 0), mission["target"])


@app.get("/")
def root():
    return {"name": "VLDST CASE X", "status": "online", "app": "/app/"}


@app.get("/health")
def health():
    if not engine:
        return {"status": "degraded", "database": False}
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": True}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": False},
        )


@app.get("/app/")
def mini():
    return FileResponse("frontend/public/index.html")


@app.get("/api/meta")
def meta():
    return {
        "name": "VLDST CASE X",
        "version": "10.1.0",
        "channel": settings.telegram_channel_url,
    }


@app.get("/api/cases")
def cases():
    return {"cases": [enrich_case(c) for c in CASES]}


@app.get("/api/profile")
def profile(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    stats = progress_stats(db, u["id"])
    level = xp_level(int(u["xp"]))
    next_xp = level * 100
    return {
        **dict(u),
        "level": level,
        "xp_to_next": max(0, next_xp - int(u["xp"])),
        "stats": stats,
    }


class OpenReq(BaseModel):
    case_code: str
    count: int = Field(1, ge=1, le=10)
    request_id: str = Field(min_length=8, max_length=128)


@app.post("/api/cases/open")
def open_case(
    req: OpenReq,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    telegram_user = tg(x_telegram_init_data)
    c = catalog_case(req.case_code)
    if not c:
        raise HTTPException(404, "Case not found")

    # Finish the read transaction created by authentication/user lookup.
    u = ensure_user(db, telegram_user)
    db.commit()

    # One transaction makes balance deduction + inventory + idempotency atomic.
    try:
        with db.begin():
            locked = db.execute(
                text("SELECT * FROM users WHERE id=:u FOR UPDATE"),
                {"u": u["id"]},
            ).mappings().first()

            old = db.execute(
                text(
                    "SELECT results_json FROM case_openings "
                    "WHERE user_id=:u AND request_id=:r"
                ),
                {"u": locked["id"], "r": req.request_id},
            ).scalar()
            if old:
                return {"results": json.loads(old), "idempotent": True}

            if locked["level"] < c["unlock_level"]:
                raise HTTPException(403, f"Нужен уровень {c['unlock_level']}")
            total = int(c["price"]) * req.count
            if int(locked["coins"]) < total:
                raise HTTPException(400, "Недостаточно монет")

            results = []
            for _ in range(req.count):
                roll = rng.random() * 100
                acc = 0.0
                rarity = "MYTHIC"
                for r, chance in RARITY_CHANCES.items():
                    acc += float(chance)
                    if roll < acc:
                        rarity = r
                        break
                candidates = [i for i in c["items"] if i["rarity"] == rarity]
                item = rng.choice(candidates)
                results.append(enrich_item(item))
                exists = db.execute(
                    text("SELECT 1 FROM items WHERE item_code=:i"),
                    {"i": item["item_code"]},
                ).scalar()
                if not exists:
                    raise HTTPException(503, "Каталог предметов не инициализирован. Повторите попытку через несколько секунд.")
                db.execute(
                    text(
                        "INSERT INTO inventory(user_id,item_code,quantity) "
                        "VALUES(:u,:i,1) "
                        "ON CONFLICT(user_id,item_code) "
                        "DO UPDATE SET quantity=inventory.quantity+1,acquired_at=NOW()"
                    ),
                    {"u": locked["id"], "i": item["item_code"]},
                )

            xp_gain = (20 if locked["xp_boost_until"] and locked["xp_boost_until"] > datetime.now(timezone.utc) else 10) * req.count
            db.execute(
                text(
                    "UPDATE users SET coins=coins-:n,xp=xp+:x,"
                    "level=(1+FLOOR((xp+:x)/100))::INT WHERE id=:u"
                ),
                {"n": total, "x": xp_gain, "u": locked["id"]},
            )
            db.execute(
                text(
                    "INSERT INTO case_openings(user_id,request_id,case_code,results_json) "
                    "VALUES(:u,:r,:c,:j)"
                ),
                {
                    "u": locked["id"],
                    "r": req.request_id,
                    "c": c["case_code"],
                    "j": json.dumps(results, ensure_ascii=False),
                },
            )
            db.execute(
                text(
                    "INSERT INTO economy_transactions(user_id,kind,amount,meta) "
                    "VALUES(:u,'CASE_OPEN',:a,:m)"
                ),
                {
                    "u": locked["id"],
                    "a": -total,
                    "m": req.case_code,
                },
            )
            db.execute(
                text(
                    "INSERT INTO economy_transactions(user_id,kind,amount,meta) "
                    "VALUES(:u,'XP_GAIN',:a,:m)"
                ),
                {
                    "u": locked["id"],
                    "a": xp_gain,
                    "m": req.case_code,
                },
            )
            db.execute(text("INSERT INTO player_world(user_id,points) VALUES(:u,:p) ON CONFLICT(user_id) DO UPDATE SET points=player_world.points+:p,updated_at=NOW()"), {"u": locked["id"], "p": req.count})
            db.execute(text("INSERT INTO item_history(user_id,item_code,action,meta) SELECT :u,item_code,'DROP',:m FROM jsonb_array_elements(:j::jsonb) x CROSS JOIN LATERAL jsonb_to_record(x) AS r(item_code text)"), {"u": locked["id"], "m": json.dumps({"case": req.case_code}), "j": json.dumps(results, ensure_ascii=False)})
            db.execute(text("UPDATE global_events SET progress=LEAST(target,progress+:p) WHERE active AND ends_at>NOW()"), {"p": req.count})
            db.execute(text("INSERT INTO event_contributions(event_id,user_id,points) SELECT id,:u,:p FROM global_events WHERE active AND ends_at>NOW() ON CONFLICT(event_id,user_id) DO UPDATE SET points=event_contributions.points+:p,updated_at=NOW()"), {"u": locked["id"], "p": req.count})
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {"ok": True, "results": results, "spent": total, "xp_gained": xp_gain, "coins_left": int(locked["coins"]) - total}


@app.get("/api/inventory")
def inventory(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    rows = db.execute(
        text(
            "SELECT i.*,it.name,it.rarity,it.sell_price,it.visual_theme,it.visual_seed "
            "FROM inventory i JOIN items it ON it.item_code=i.item_code "
            "WHERE i.user_id=:u AND i.quantity>0 ORDER BY i.acquired_at DESC"
        ),
        {"u": u["id"]},
    ).mappings()
    return {"items": [enrich_item(dict(r)) for r in rows]}


class SellReq(BaseModel):
    item_code: str
    quantity: int = Field(1, ge=1)


class PinReq(BaseModel):
    item_code: str
    pinned: bool


@app.post("/api/inventory/pin")
def pin_inventory(
    req: PinReq,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    result = db.execute(
        text(
            "UPDATE inventory SET pinned=:p "
            "WHERE user_id=:u AND item_code=:i AND quantity>0"
        ),
        {"p": req.pinned, "u": u["id"], "i": req.item_code},
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Предмет не найден")
    return {"ok": True, "item_code": req.item_code, "pinned": req.pinned}


@app.post("/api/inventory/sell")
def sell(
    req: SellReq,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    db.commit()
    try:
        with db.begin():
            r = db.execute(
                text(
                    "SELECT i.quantity,i.pinned,it.sell_price "
                    "FROM inventory i JOIN items it ON it.item_code=i.item_code "
                    "WHERE i.user_id=:u AND i.item_code=:i FOR UPDATE"
                ),
                {"u": u["id"], "i": req.item_code},
            ).mappings().first()
            if not r or int(r["quantity"]) < req.quantity:
                raise HTTPException(400, "Недостаточно предметов")
            if r["pinned"]:
                raise HTTPException(400, "Предмет закреплён")
            gain = int(r["sell_price"]) * req.quantity
            db.execute(
                text(
                    "UPDATE inventory SET quantity=quantity-:q "
                    "WHERE user_id=:u AND item_code=:i"
                ),
                {"q": req.quantity, "u": u["id"], "i": req.item_code},
            )
            db.execute(
                text("UPDATE users SET coins=coins+:g WHERE id=:u"),
                {"g": gain, "u": u["id"]},
            )
            db.execute(
                text(
                    "INSERT INTO economy_transactions(user_id,kind,amount,meta) "
                    "VALUES(:u,'ITEM_SELL',:a,:m)"
                ),
                {"u": u["id"], "a": gain, "m": req.item_code},
            )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return {"ok": True, "coins_gained": gain}


@app.get("/api/collection")
def collection(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    owned = {
        r["item_code"]: int(r["quantity"])
        for r in db.execute(
            text("SELECT item_code,quantity FROM inventory WHERE user_id=:u"),
            {"u": u["id"]},
        ).mappings()
    }
    return {
        "items": [
            {
                **enrich_item(i),
                "owned": i["item_code"] in owned,
                "quantity": owned.get(i["item_code"], 0),
            }
            for c in CASES
            for i in c["items"]
        ]
    }


@app.get("/api/daily")
def daily_status(x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    today=date.today()
    last=u["last_daily"]
    last_date=getattr(last,"date",lambda:last)() if last is not None else None
    return {"claimed": last_date==today, "streak": int(u["daily_streak"] or 0), "last_daily": str(last_date) if last_date else None}

@app.post("/api/daily")
def daily(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    db.commit()
    today = date.today()
    try:
        with db.begin():
            locked = db.execute(
                text("SELECT * FROM users WHERE id=:u FOR UPDATE"),
                {"u": u["id"]},
            ).mappings().first()
            last_daily = locked["last_daily"]
            if last_daily is not None and getattr(last_daily, "date", lambda: last_daily)() == today:
                raise HTTPException(400, "Ежедневная награда уже получена")
            last = locked["last_daily"]
            streak = int(locked["daily_streak"] or 0)
            if last is not None and (today - last).days > 1:
                streak = 0
            streak += 1
            reward = [500, 750, 1000, 1500, 2000, 3000, 5000][(streak - 1) % 7]
            db.execute(
                text(
                    "UPDATE users SET coins=coins+:c,last_daily=:d,daily_streak=:s "
                    "WHERE id=:u"
                ),
                {"c": reward, "d": today, "s": streak, "u": u["id"]},
            )
            db.execute(
                text(
                    "INSERT INTO economy_transactions(user_id,kind,amount,meta) "
                    "VALUES(:u,'DAILY',:a,:m)"
                ),
                {"u": u["id"], "a": reward, "m": f"day:{(streak-1)%7+1}"},
            )
    except HTTPException:
        db.rollback()
        raise
    return {
        "ok": True,
        "day": (streak - 1) % 7 + 1,
        "coins": reward,
        "streak": streak,
    }


@app.get("/api/missions")
def missions(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    stats = progress_stats(db, u["id"])
    claimed = {
        r["mission_id"]
        for r in db.execute(
            text("SELECT mission_id FROM mission_claims WHERE user_id=:u"),
            {"u": u["id"]},
        ).mappings()
    }
    return {
        "daily": [
            {
                **m,
                "progress": mission_progress(stats, m),
                "claimed": m["id"] in claimed,
                "ready": mission_progress(stats, m) >= m["target"]
                and m["id"] not in claimed,
            }
            for m in MISSION_CATALOG
        ]
    }


@app.post("/api/missions/{mission_id}/claim")
def claim_mission(
    mission_id: str,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    mission = next((m for m in MISSION_CATALOG if m["id"] == mission_id), None)
    if not mission:
        raise HTTPException(404, "Mission not found")
    u = current_user(db, x_telegram_init_data)
    db.commit()
    try:
        with db.begin():
            stats = progress_stats(db, u["id"])
            if mission_progress(stats, mission) < mission["target"]:
                raise HTTPException(400, "Задание ещё не выполнено")
            exists = db.execute(
                text(
                    "SELECT 1 FROM mission_claims WHERE user_id=:u AND mission_id=:m"
                ),
                {"u": u["id"], "m": mission_id},
            ).scalar()
            if exists:
                raise HTTPException(400, "Награда уже получена")
            db.execute(
                text(
                    "INSERT INTO mission_claims(user_id,mission_id,reward) "
                    "VALUES(:u,:m,:r)"
                ),
                {"u": u["id"], "m": mission_id, "r": mission["reward"]},
            )
            db.execute(
                text("UPDATE users SET coins=coins+:r WHERE id=:u"),
                {"r": mission["reward"], "u": u["id"]},
            )
    except HTTPException:
        db.rollback()
        raise
    return {"ok": True, "reward": mission["reward"]}


@app.get("/api/achievements")
def achievements(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    stats = progress_stats(db, u["id"])
    claimed = {
        r["achievement_id"]
        for r in db.execute(
            text("SELECT achievement_id FROM achievement_claims WHERE user_id=:u"),
            {"u": u["id"]},
        ).mappings()
    }
    return {
        "achievements": [
            {
                **a,
                "progress": min(stats.get(a["kind"], 0), a["target"]),
                "claimed": a["id"] in claimed,
                "ready": stats.get(a["kind"], 0) >= a["target"]
                and a["id"] not in claimed,
            }
            for a in ACHIEVEMENT_CATALOG
        ]
    }


@app.post("/api/achievements/{achievement_id}/claim")
def claim_achievement(
    achievement_id: str,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    achievement = next(
        (a for a in ACHIEVEMENT_CATALOG if a["id"] == achievement_id), None
    )
    if not achievement:
        raise HTTPException(404, "Achievement not found")
    u = current_user(db, x_telegram_init_data)
    db.commit()
    try:
        with db.begin():
            stats = progress_stats(db, u["id"])
            if stats.get(achievement["kind"], 0) < achievement["target"]:
                raise HTTPException(400, "Достижение ещё не выполнено")
            exists = db.execute(
                text(
                    "SELECT 1 FROM achievement_claims "
                    "WHERE user_id=:u AND achievement_id=:a"
                ),
                {"u": u["id"], "a": achievement_id},
            ).scalar()
            if exists:
                raise HTTPException(400, "Награда уже получена")
            db.execute(
                text(
                    "INSERT INTO achievement_claims(user_id,achievement_id,reward) "
                    "VALUES(:u,:a,:r)"
                ),
                {"u": u["id"], "a": achievement_id, "r": achievement["reward"]},
            )
            db.execute(
                text("UPDATE users SET coins=coins+:r WHERE id=:u"),
                {"r": achievement["reward"], "u": u["id"]},
            )
    except HTTPException:
        db.rollback()
        raise
    return {"ok": True, "reward": achievement["reward"]}


@app.get("/api/season")
def season(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    level = min(50, max(1, xp_level(int(u["xp"]))))
    claimed = {
        (int(r["level"]), bool(r["premium"]))
        for r in db.execute(
            text("SELECT level,premium FROM season_claims WHERE user_id=:u"),
            {"u": u["id"]},
        ).mappings()
    }
    return {
        "name": "VLDST SEASON 1",
        "levels": 50,
        "free": True,
        "premium": bool(u["premium"]),
        "current_level": level,
        "xp": int(u["xp"]),
        "rewards": [
            {
                **r,
                "free_claimed": (r["level"], False) in claimed,
                "premium_claimed": (r["level"], True) in claimed,
                "ready": r["level"] <= level,
            }
            for r in SEASON_REWARDS
        ],
    }


class SeasonClaimReq(BaseModel):
    level: int = Field(ge=1, le=50)
    premium: bool = False


@app.post("/api/season/claim")
def claim_season(
    req: SeasonClaimReq,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    db.commit()
    try:
        with db.begin():
            locked = db.execute(
                text("SELECT * FROM users WHERE id=:u FOR UPDATE"),
                {"u": u["id"]},
            ).mappings().first()
            if xp_level(int(locked["xp"])) < req.level:
                raise HTTPException(400, "Уровень сезона ещё не достигнут")
            if req.premium and not locked["premium"]:
                raise HTTPException(403, "Нужен Premium")
            exists = db.execute(
                text(
                    "SELECT 1 FROM season_claims WHERE user_id=:u AND level=:l"
                ),
                {"u": u["id"], "l": req.level},
            ).scalar()
            if exists:
                raise HTTPException(400, "Награда уже получена")
            reward = SEASON_REWARDS[req.level - 1]["premium" if req.premium else "free"]
            db.execute(
                text(
                    "INSERT INTO season_claims(user_id,level,reward,premium) "
                    "VALUES(:u,:l,:r,:p)"
                ),
                {"u": u["id"], "l": req.level, "r": reward, "p": req.premium},
            )
            db.execute(
                text("UPDATE users SET coins=coins+:r WHERE id=:u"),
                {"r": reward, "u": u["id"]},
            )
    except HTTPException:
        db.rollback()
        raise
    return {"ok": True, "reward": reward}


@app.get("/api/shop")
def shop():
    return {"products": SHOP_PRODUCTS}


class ShopReq(BaseModel):
    product_id: str


@app.post("/api/shop/invoice")
async def shop_invoice(
    req: ShopReq,
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    if not settings.bot_token:
        raise HTTPException(503, "BOT_TOKEN is not configured")
    product = next((p for p in SHOP_PRODUCTS if p["id"] == req.product_id), None)
    if not product:
        raise HTTPException(404, "Product not found")
    u = current_user(db, x_telegram_init_data)
    from aiogram import Bot
    from aiogram.types import LabeledPrice

    payload = f"shop:{product['id']}:{u['id']}:{rng.randrange(10**8, 10**9)}"
    bot = Bot(settings.bot_token)
    try:
        link = await bot.create_invoice_link(
            title=f"VLDST {product['title']}",
            description=product["description"],
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=product["title"], amount=product["stars"])],
        )
    finally:
        await bot.session.close()
    return {"ok": True, "invoice_url": link}


@app.get("/api/referrals")
def referrals(
    x_telegram_init_data: str = Header(...),
    db: Session = Depends(get_db),
):
    u = current_user(db, x_telegram_init_data)
    r = db.execute(
        text(
            "SELECT COUNT(*) invited,COALESCE(SUM(earned),0) earned,"
            "COUNT(*) FILTER(WHERE active) active "
            "FROM referrals WHERE referrer_id=:u"
        ),
        {"u": u["id"]},
    ).mappings().first()
    return {
        **dict(r),
        "link": f"https://t.me/VLDST_CASE_Xbot?start=ref_{u['id']}",
    }



class PromoReq(BaseModel):
    code: str = Field(min_length=3, max_length=40)

@app.post("/api/promo/redeem")
def redeem_promo(req: PromoReq, x_telegram_init_data: str = Header(...), db: Session = Depends(get_db)):
    u = current_user(db, x_telegram_init_data)
    db.commit()
    code = req.code.strip().upper()
    try:
        with db.begin():
            promo = db.execute(text("SELECT * FROM promo_codes WHERE code=:c FOR UPDATE"), {"c": code}).mappings().first()
            if not promo or not promo["active"]:
                raise HTTPException(404, "Промокод не найден или отключён")
            if promo["expires_at"] is not None and promo["expires_at"] <= datetime.now(timezone.utc):
                raise HTTPException(400, "Срок действия промокода истёк")
            if int(promo["used_count"]) >= int(promo["max_uses"]):
                raise HTTPException(400, "Лимит промокода исчерпан")
            exists = db.execute(text("SELECT 1 FROM promo_redemptions WHERE promo_id=:p AND user_id=:u"), {"p": promo["id"], "u": u["id"]}).first()
            if exists:
                raise HTTPException(400, "Ты уже использовал этот промокод")
            db.execute(text("INSERT INTO promo_redemptions(promo_id,user_id) VALUES(:p,:u)"), {"p": promo["id"], "u": u["id"]})
            db.execute(text("UPDATE promo_codes SET used_count=used_count+1 WHERE id=:p"), {"p": promo["id"]})
            db.execute(text("UPDATE users SET coins=coins+:c,xp=xp+:x,premium=(premium OR :pr) WHERE id=:u"), {"c": promo["reward_coins"], "x": promo["reward_xp"], "pr": bool(promo["reward_premium"]), "u": u["id"]})
            if promo["reward_coins"]:
                db.execute(text("INSERT INTO economy_transactions(user_id,kind,amount,meta) VALUES(:u,'PROMO',:a,:m)"), {"u": u["id"], "a": promo["reward_coins"], "m": code})
    except HTTPException:
        db.rollback(); raise
    return {"ok": True, "coins": int(promo["reward_coins"]), "xp": int(promo["reward_xp"]), "premium": bool(promo["reward_premium"])}

@app.get("/api/history")
def history(x_telegram_init_data: str = Header(...), db: Session = Depends(get_db)):
    u = current_user(db, x_telegram_init_data)
    tx = [dict(r) for r in db.execute(text("SELECT kind,amount,meta,created_at FROM economy_transactions WHERE user_id=:u ORDER BY created_at DESC LIMIT 40"), {"u": u["id"]}).mappings()]
    openings = [dict(r) for r in db.execute(text("SELECT case_code,created_at FROM case_openings WHERE user_id=:u ORDER BY created_at DESC LIMIT 20"), {"u": u["id"]}).mappings()]
    return {"transactions": tx, "openings": openings}

@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    return {
        "users": [
            dict(r)
            for r in db.execute(
                text(
                    "SELECT username,first_name,level,xp,coins FROM users "
                    "ORDER BY xp DESC,coins DESC LIMIT 50"
                )
            ).mappings()
        ]
    }


# ---------------- V10 WORLD / DNA / SOCIAL SYSTEMS ----------------
FACTIONS = {
    "INFERNO": {"emoji": "🔥", "title": "INFERNO"},
    "NEON": {"emoji": "⚡", "title": "NEON"},
    "GALAXY": {"emoji": "🌌", "title": "GALAXY"},
    "DRAGON": {"emoji": "🐉", "title": "DRAGON"},
}


def _ensure_v10_user(db: Session, user_id: int):
    db.execute(text("INSERT INTO player_world(user_id) VALUES(:u) ON CONFLICT DO NOTHING"), {"u": user_id})
    db.execute(text("INSERT INTO player_dna(user_id) VALUES(:u) ON CONFLICT DO NOTHING"), {"u": user_id})


def _update_dna(db: Session, user_id: int):
    rows = db.execute(text("""
        SELECT COALESCE(SUM(CASE WHEN c.theme ILIKE '%inferno%' THEN i.quantity ELSE 0 END),0) inferno,
               COALESCE(SUM(CASE WHEN c.theme ILIKE '%cyber%' OR c.theme ILIKE '%neon%' THEN i.quantity ELSE 0 END),0) neon,
               COALESCE(SUM(CASE WHEN c.theme ILIKE '%galaxy%' THEN i.quantity ELSE 0 END),0) galaxy,
               COUNT(DISTINCT CASE WHEN i.quantity > 0 THEN i.item_code END) collector
        FROM inventory i JOIN items it ON it.item_code=i.item_code JOIN cases c ON c.case_code=it.case_code
        WHERE i.user_id=:u
    """), {"u": user_id}).mappings().first()
    social = db.execute(text("SELECT COUNT(*) FROM referrals WHERE referrer_id=:u AND active"), {"u": user_id}).scalar() or 0
    vals = {"u": user_id, **dict(rows), "social": social}
    db.execute(text("""UPDATE player_dna SET inferno=:inferno,neon=:neon,galaxy=:galaxy,collector=:collector,social=:social,updated_at=NOW() WHERE user_id=:u"""), vals)


@app.get("/api/world")
def world(x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); _ensure_v10_user(db,u["id"]); _update_dna(db,u["id"]); db.commit()
    w=dict(db.execute(text("SELECT * FROM player_world WHERE user_id=:u"),{"u":u["id"]}).mappings().first())
    dna=dict(db.execute(text("SELECT inferno,neon,galaxy,collector,social FROM player_dna WHERE user_id=:u"),{"u":u["id"]}).mappings().first())
    f=db.execute(text("SELECT faction FROM player_factions WHERE user_id=:u"),{"u":u["id"]}).scalar()
    event=db.execute(text("SELECT code,title,description,target,progress,reward,ends_at FROM global_events WHERE active AND ends_at>NOW() ORDER BY ends_at LIMIT 1")).mappings().first()
    factions=[{**v,"code":k,"points":int(db.execute(text("SELECT COALESCE(SUM(points),0) FROM event_contributions ec JOIN player_factions pf ON pf.user_id=ec.user_id WHERE pf.faction=:f"),{"f":k}).scalar() or 0)} for k,v in FACTIONS.items()]
    return {"world":w,"dna":dna,"faction":f,"factions":factions,"event":dict(event) if event else None}


class FactionReq(BaseModel):
    faction: str

@app.post("/api/world/faction")
def choose_faction(req:FactionReq,x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); code=req.faction.upper()
    if code not in FACTIONS: raise HTTPException(400,"Неизвестная фракция")
    exists=db.execute(text("SELECT faction FROM player_factions WHERE user_id=:u"),{"u":u["id"]}).scalar()
    if exists: raise HTTPException(400,"Фракция уже выбрана")
    db.execute(text("INSERT INTO player_factions(user_id,faction) VALUES(:u,:f)"),{"u":u["id"],"f":code}); db.commit()
    return {"ok":True,"faction":code}


@app.get("/api/dna")
def dna(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); _ensure_v10_user(db,u["id"]); _update_dna(db,u["id"]); db.commit()
    return dict(db.execute(text("SELECT inferno,neon,galaxy,collector,social FROM player_dna WHERE user_id=:u"),{"u":u["id"]}).mappings().first())


@app.get("/api/legacy")
def legacy(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    return {"legacy_level":int(u["legacy_level"]),"level":int(u["level"]),"can_ascend":int(u["level"])>=100,"bonus":int(u["legacy_level"])*5}

@app.post("/api/legacy/ascend")
def legacy_ascend(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    if int(u["level"])<100: raise HTTPException(400,"Legacy доступен с 100 уровня")
    new_legacy=int(u["legacy_level"])+1
    db.execute(text("UPDATE users SET legacy_level=:l,level=1,xp=0,coins=GREATEST(5000,coins/10) WHERE id=:u"),{"l":new_legacy,"u":u["id"]})
    db.execute(text("INSERT INTO economy_transactions(user_id,kind,amount,meta) VALUES(:u,'LEGACY',0,:m)"),{"u":u["id"],"m":str(new_legacy)})
    db.commit(); return {"ok":True,"legacy_level":new_legacy}


@app.get("/api/events")
def events(db:Session=Depends(get_db)):
    rows=db.execute(text("SELECT code,title,description,target,progress,reward,ends_at FROM global_events WHERE active ORDER BY ends_at")).mappings()
    return {"events":[dict(r) for r in rows]}

@app.post("/api/events/contribute")
def contribute_event(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); ev=db.execute(text("SELECT * FROM global_events WHERE active AND ends_at>NOW() ORDER BY ends_at LIMIT 1 FOR UPDATE")).mappings().first()
    if not ev: raise HTTPException(404,"Нет активного события")
    points=1
    db.execute(text("UPDATE global_events SET progress=progress+:p WHERE id=:e"),{"p":points,"e":ev["id"]})
    db.execute(text("INSERT INTO event_contributions(event_id,user_id,points) VALUES(:e,:u,:p) ON CONFLICT(event_id,user_id) DO UPDATE SET points=event_contributions.points+:p,updated_at=NOW()"),{"e":ev["id"],"u":u["id"],"p":points})
    db.execute(text("UPDATE player_world SET points=points+:p,updated_at=NOW() WHERE user_id=:u"),{"p":points,"u":u["id"]})
    db.commit(); return {"ok":True,"points":points}


@app.get("/api/forge")
def forge(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    current_user(db,x_telegram_init_data)
    return {"recipes":[dict(r) for r in db.execute(text("SELECT recipe_id,title,result_item_code,ingredients,cost FROM forge_recipes WHERE active ORDER BY recipe_id")).mappings()]}

class ForgeReq(BaseModel):
    recipe_id:str

@app.post("/api/forge/craft")
def forge_craft(req:ForgeReq,x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    recipe=db.execute(text("SELECT * FROM forge_recipes WHERE recipe_id=:r AND active"),{"r":req.recipe_id}).mappings().first()
    if not recipe: raise HTTPException(404,"Рецепт не найден")
    ingredients=recipe["ingredients"] if isinstance(recipe["ingredients"],dict) else json.loads(recipe["ingredients"])
    with db.begin():
        locked=db.execute(text("SELECT coins FROM users WHERE id=:u FOR UPDATE"),{"u":u["id"]}).mappings().first()
        if int(locked["coins"])<int(recipe["cost"]): raise HTTPException(400,"Недостаточно монет")
        for code,qty in ingredients.items():
            have=db.execute(text("SELECT quantity FROM inventory WHERE user_id=:u AND item_code=:i"),{"u":u["id"],"i":code}).scalar() or 0
            if int(have)<int(qty): raise HTTPException(400,f"Нужно {qty} × {code}")
        for code,qty in ingredients.items(): db.execute(text("UPDATE inventory SET quantity=quantity-:q WHERE user_id=:u AND item_code=:i"),{"q":qty,"u":u["id"],"i":code})
        result=recipe["result_item_code"]
        db.execute(text("INSERT INTO inventory(user_id,item_code,quantity) VALUES(:u,:i,1) ON CONFLICT(user_id,item_code) DO UPDATE SET quantity=inventory.quantity+1,acquired_at=NOW()"),{"u":u["id"],"i":result})
        db.execute(text("UPDATE users SET coins=coins-:c WHERE id=:u"),{"c":recipe["cost"],"u":u["id"]})
        db.execute(text("INSERT INTO item_history(user_id,item_code,action,meta) VALUES(:u,:i,'CRAFT',:m)"),{"u":u["id"],"i":result,"m":json.dumps({"recipe":req.recipe_id})})
    return {"ok":True,"item_code":result}


@app.get("/api/item-history/{item_code}")
def item_history(item_code:str,x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    current_user(db,x_telegram_init_data)
    rows=db.execute(text("SELECT action,meta,created_at FROM item_history WHERE item_code=:i ORDER BY created_at DESC LIMIT 50"),{"i":item_code}).mappings()
    return {"item_code":item_code,"history":[dict(r) for r in rows]}


@app.get("/api/secret-sets")
def secret_sets(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    rows=db.execute(text("SELECT item_code,quantity FROM inventory WHERE user_id=:u AND quantity>0"),{"u":u["id"]}).mappings()
    owned={r["item_code"] for r in rows}
    # Secret sets use the first three items from selected themed series; easy to extend without schema changes.
    sets=[]
    for prefix,title,reward in [("VLDST-IN","INFERNO HUNTER",5000),("VLDST-CY","NEON HUNTER",5000),("VLDST-GA","GALAXY SEEKER",7500),("VLDST-DR","DRAGON LORD",10000)]:
        codes=[f"{prefix}-{i:03d}" for i in range(1,4)]
        got=sum(c in owned for c in codes)
        sets.append({"code":prefix,"title":title,"owned":got,"total":3,"discovered":got==3,"reward":reward})
    return {"sets":sets}


@app.get("/api/creator")
def creator(x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    row=db.execute(text("SELECT code,uses,reward,active FROM creator_codes WHERE owner_user_id=:u ORDER BY created_at DESC LIMIT 1"),{"u":u["id"]}).mappings().first()
    return {"code":dict(row) if row else None}

class CreatorReq(BaseModel):
    code:str=Field(min_length=3,max_length=24)

@app.post("/api/creator")
def create_creator(req:CreatorReq,x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); code=req.code.strip().upper()
    if db.execute(text("SELECT 1 FROM creator_codes WHERE code=:c"),{"c":code}).scalar(): raise HTTPException(400,"Код уже занят")
    db.execute(text("INSERT INTO creator_codes(code,owner_user_id,reward) VALUES(:c,:u,1000)"),{"c":code,"u":u["id"]}); db.commit(); return {"ok":True,"code":code}

class CreatorUseReq(BaseModel):
    code:str

@app.post("/api/creator/use")
def use_creator(req:CreatorUseReq,x_telegram_init_data:str=Header(...),db:Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); code=req.code.strip().upper()
    row=db.execute(text("SELECT * FROM creator_codes WHERE code=:c AND active FOR UPDATE"),{"c":code}).mappings().first()
    if not row: raise HTTPException(404,"Код не найден")
    try:
        with db.begin():
            db.execute(text("INSERT INTO creator_uses(code,user_id) VALUES(:c,:u)"),{"c":code,"u":u["id"]})
            db.execute(text("UPDATE creator_codes SET uses=uses+1 WHERE code=:c"),{"c":code})
            db.execute(text("UPDATE users SET coins=coins+:r WHERE id=:u"),{"r":row["reward"],"u":u["id"]})
    except Exception: db.rollback(); raise HTTPException(400,"Код уже использован")
    return {"ok":True,"reward":int(row["reward"])}


# Seed one global event and simple forge recipes after normal catalog seed.
def seed_v10(db: Session):
    db.execute(text("""INSERT INTO global_events(code,title,description,target,progress,reward,ends_at,active) VALUES('DRAGON_INVASION','DRAGON INVASION','Откройте кейсы вместе и заполните шкалу события.',1000000,0,5000,NOW()+INTERVAL '7 days',TRUE) ON CONFLICT(code) DO NOTHING"""))
    rows=db.execute(text("SELECT item_code FROM items WHERE item_code LIKE 'VLDST-IN-%' ORDER BY item_code LIMIT 3")).scalars().all()
    if len(rows)>=3:
        db.execute(text("""INSERT INTO forge_recipes(recipe_id,title,result_item_code,ingredients,cost) VALUES('inferno_core','INFERNO CORE',:r,:ing,1000) ON CONFLICT(recipe_id) DO NOTHING"""),{"r":rows[2],"ing":json.dumps({rows[0]:1,rows[1]:1})})
    db.commit()


# ---------------- V9 FINAL RELEASE ADMIN / PLATFORM ----------------
def admin_ids():
    # Owner-only access. Keep the owner ID fixed in code so the WebApp cannot
    # accidentally expose the admin panel to another configured account.
    return {6038067496}

def require_admin(db: Session, raw: str):
    user = current_user(db, raw)
    if int(user["telegram_id"]) not in admin_ids():
        raise HTTPException(403, "Admin access required")
    return user

class AdminBalanceReq(BaseModel):
    telegram_id: int
    amount: int = Field(ge=-10_000_000, le=10_000_000)
    reason: str = Field(default="admin", max_length=200)

class AdminBlockReq(BaseModel):
    telegram_id: int
    blocked: bool

class AdReq(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    reward: int = Field(ge=0, le=1_000_000)
    url: str = Field(default="", max_length=500)
    daily_limit: int = Field(default=1, ge=1, le=100)
    cooldown_seconds: int = Field(default=86400, ge=0, le=2592000)
    active: bool = True

class AdClaimReq(BaseModel):
    ad_id: int

class GameReq(BaseModel):
    game_code: str = Field(default="neon_reactor", min_length=3, max_length=40)
    score: int = Field(default=0, ge=0, le=100)
    request_id: str = Field(min_length=8, max_length=128)

@app.get("/api/admin/me")
def admin_me(x_telegram_init_data: str = Header(...), db: Session = Depends(get_db)):
    u=require_admin(db,x_telegram_init_data)
    return {"ok":True,"admin":dict(u)}

@app.get("/api/admin/dashboard")
def admin_dashboard(x_telegram_init_data: str = Header(...), db: Session = Depends(get_db)):
    a=require_admin(db,x_telegram_init_data)
    stats=db.execute(text("SELECT (SELECT COUNT(*) FROM users) users,(SELECT COALESCE(SUM(coins),0) FROM users) coins,(SELECT COUNT(*) FROM case_openings) openings,(SELECT COUNT(*) FROM payments WHERE status='PAID') payments")).mappings().one()
    return {"ok":True,"stats":dict(stats),"admin_id":a["telegram_id"]}

@app.get("/api/admin/users")
def admin_users(x_telegram_init_data: str = Header(...), db: Session = Depends(get_db)):
    require_admin(db,x_telegram_init_data)
    rows=db.execute(text("SELECT id,telegram_id,username,first_name,coins,xp,level,premium,season_pass,COALESCE(blocked,FALSE) blocked,created_at FROM users ORDER BY created_at DESC LIMIT 100")).mappings()
    return {"users":[dict(r) for r in rows]}

@app.post("/api/admin/balance")
def admin_balance(req: AdminBalanceReq,x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    a=require_admin(db,x_telegram_init_data); db.commit()
    try:
        with db.begin():
            u=db.execute(text("SELECT id FROM users WHERE telegram_id=:t FOR UPDATE"),{"t":req.telegram_id}).mappings().first()
            if not u: raise HTTPException(404,"User not found")
            if req.amount<0:
                ok=db.execute(text("UPDATE users SET coins=coins+:a WHERE id=:u AND coins>=:need"),{"a":req.amount,"need":-req.amount,"u":u["id"]})
                if ok.rowcount==0: raise HTTPException(400,"Недостаточно монет")
            else: db.execute(text("UPDATE users SET coins=coins+:a WHERE id=:u"),{"a":req.amount,"u":u["id"]})
            db.execute(text("INSERT INTO economy_transactions(user_id,kind,amount,meta) VALUES(:u,'ADMIN_ADJUST',:a,:m)"),{"u":u["id"],"a":req.amount,"m":req.reason})
            db.execute(text("INSERT INTO admin_audit(admin_user_id,action,target_user_id,meta) VALUES(:a,'BALANCE',:u,:m)"),{"a":a["id"],"u":u["id"],"m":json.dumps({"amount":req.amount,"reason":req.reason})})
    except HTTPException: db.rollback(); raise
    return {"ok":True}

class AdminAdUpdateReq(BaseModel):
    active: Optional[bool] = None
    reward: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    daily_limit: Optional[int] = Field(default=None, ge=1, le=100)
    cooldown_seconds: Optional[int] = Field(default=None, ge=0, le=2_592_000)

class AdminUserStatusReq(BaseModel):
    telegram_id: int
    blocked: bool


class AdminGrantItemReq(BaseModel):
    telegram_id: int
    item_code: str = Field(min_length=3, max_length=80)
    quantity: int = Field(default=1, ge=1, le=100000)

class AdminPromoReq(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    reward_coins: int = Field(default=0, ge=0, le=100000000)
    reward_xp: int = Field(default=0, ge=0, le=1000000)
    reward_premium: bool = False
    max_uses: int = Field(default=1, ge=1, le=1000000)
    expires_at: Optional[datetime] = None

@app.post("/api/admin/inventory/grant")
def admin_grant_item(req: AdminGrantItemReq, x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    a = require_admin(db, x_telegram_init_data)
    db.commit()
    try:
        with db.begin():
            u = db.execute(text("SELECT id FROM users WHERE telegram_id=:t FOR UPDATE"), {"t": req.telegram_id}).mappings().first()
            item = db.execute(text("SELECT item_code FROM items WHERE item_code=:i"), {"i": req.item_code}).mappings().first()
            if not u: raise HTTPException(404, "User not found")
            if not item: raise HTTPException(404, "Item not found")
            db.execute(text("INSERT INTO inventory(user_id,item_code,quantity) VALUES(:u,:i,:q) ON CONFLICT(user_id,item_code) DO UPDATE SET quantity=inventory.quantity+:q"), {"u": u["id"], "i": req.item_code, "q": req.quantity})
            db.execute(text("INSERT INTO admin_audit(admin_user_id,action,target_user_id,meta) VALUES(:a,'GRANT_ITEM',:u,:m)"), {"a": a["id"], "u": u["id"], "m": json.dumps({"item_code": req.item_code, "quantity": req.quantity})})
    except HTTPException:
        db.rollback(); raise
    return {"ok": True}

@app.get("/api/admin/promos")
def admin_promos(x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    require_admin(db, x_telegram_init_data)
    return {"promos": [dict(r) for r in db.execute(text("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 100")).mappings()]}

@app.post("/api/admin/promos")
def admin_create_promo(req: AdminPromoReq, x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    a = require_admin(db, x_telegram_init_data)
    code = req.code.strip().upper()
    row = db.execute(text("INSERT INTO promo_codes(code,reward_coins,reward_xp,reward_premium,max_uses,expires_at) VALUES(:c,:coins,:xp,:pr,:m,:e) RETURNING id"), {"c":code,"coins":req.reward_coins,"xp":req.reward_xp,"pr":req.reward_premium,"m":req.max_uses,"e":req.expires_at}).scalar_one()
    db.execute(text("INSERT INTO admin_audit(admin_user_id,action,meta) VALUES(:a,'CREATE_PROMO',:m)"), {"a": a["id"], "m": json.dumps({"code":code,"id":row})})
    db.commit()
    return {"ok":True,"id":row}

@app.patch("/api/admin/promos/{promo_id}")
def admin_toggle_promo(promo_id:int, active:bool, x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    a=require_admin(db,x_telegram_init_data)
    row=db.execute(text("UPDATE promo_codes SET active=:a WHERE id=:id RETURNING id,active"),{"a":active,"id":promo_id}).mappings().first()
    if not row: raise HTTPException(404,"Promo not found")
    db.execute(text("INSERT INTO admin_audit(admin_user_id,action,meta) VALUES(:a,'TOGGLE_PROMO',:m)"),{"a":a["id"],"m":json.dumps(dict(row))}); db.commit()
    return {"ok":True,"promo":dict(row)}

@app.get("/api/admin/audit")
def admin_audit(x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    require_admin(db,x_telegram_init_data)
    rows=db.execute(text("SELECT id,admin_user_id,action,target_user_id,meta,created_at FROM admin_audit ORDER BY created_at DESC LIMIT 100")).mappings()
    return {"audit":[dict(r) for r in rows]}

@app.get("/api/admin/catalog")
def admin_catalog(x_telegram_init_data: str=Header(...), db: Session=Depends(get_db)):
    require_admin(db,x_telegram_init_data)
    rows=db.execute(text("SELECT c.case_code,c.name,c.price,c.theme,c.unlock_level,c.active,COUNT(i.item_code) items FROM cases c LEFT JOIN items i ON i.case_code=c.case_code GROUP BY c.case_code ORDER BY c.unlock_level,c.case_code")).mappings()
    return {"cases":[dict(r) for r in rows]}

@app.post("/api/admin/users/status")
def admin_user_status(req: AdminUserStatusReq,x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    a=require_admin(db,x_telegram_init_data)
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked BOOLEAN NOT NULL DEFAULT FALSE"))
    row=db.execute(text("UPDATE users SET blocked=:b WHERE telegram_id=:t RETURNING id,telegram_id,blocked"),{"b":req.blocked,"t":req.telegram_id}).mappings().first()
    if not row: raise HTTPException(404,"User not found")
    db.execute(text("INSERT INTO admin_audit(admin_user_id,action,target_user_id,meta) VALUES(:a,:action,:u,:m)"),{"a":a["id"],"action":"BLOCK" if req.blocked else "UNBLOCK","u":row["id"],"m":json.dumps({"telegram_id":req.telegram_id})})
    db.commit()
    return {"ok":True,"user":dict(row)}

@app.patch("/api/admin/ads/{ad_id}")
def admin_update_ad(ad_id:int,req:AdminAdUpdateReq,x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    a=require_admin(db,x_telegram_init_data)
    fields=[]; params={"id":ad_id}
    for name in ("active","reward","daily_limit","cooldown_seconds"):
        value=getattr(req,name)
        if value is not None:
            fields.append(f"{name}=:{name}"); params[name]=value
    if not fields: raise HTTPException(400,"No changes supplied")
    row=db.execute(text(f"UPDATE ad_campaigns SET {', '.join(fields)} WHERE id=:id RETURNING *"),params).mappings().first()
    if not row: raise HTTPException(404,"Ad not found")
    db.execute(text("INSERT INTO admin_audit(admin_user_id,action,meta) VALUES(:a,'UPDATE_AD',:m)"),{"a":a["id"],"m":json.dumps({"id":ad_id,"changes":params})})
    db.commit()
    return {"ok":True,"ad":dict(row)}

@app.get("/api/ads")
def ads(x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data)
    rows=db.execute(text("SELECT a.id,a.title,a.description,a.reward,a.url,a.daily_limit,a.cooldown_seconds,a.active, (SELECT COUNT(*) FROM ad_claims c WHERE c.user_id=:u AND c.ad_id=a.id AND c.claimed_at::date=CURRENT_DATE) claimed_today FROM ad_campaigns a WHERE a.active ORDER BY a.id DESC"),{"u":u["id"]}).mappings()
    return {"ads":[dict(r) for r in rows]}

@app.post("/api/ads/claim")
def claim_ad(req: AdClaimReq,x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); db.commit()
    try:
        with db.begin():
            ad=db.execute(text("SELECT * FROM ad_campaigns WHERE id=:a AND active FOR UPDATE"),{"a":req.ad_id}).mappings().first()
            if not ad: raise HTTPException(404,"Ad not found")
            count=db.execute(text("SELECT COUNT(*) FROM ad_claims WHERE user_id=:u AND ad_id=:a AND claimed_at::date=CURRENT_DATE"),{"u":u["id"],"a":req.ad_id}).scalar_one()
            if int(count)>=int(ad["daily_limit"]): raise HTTPException(400,"Лимит на сегодня исчерпан")
            recent=db.execute(text("SELECT 1 FROM ad_claims WHERE user_id=:u AND ad_id=:a AND claimed_at>NOW()-(:s * INTERVAL '1 second') LIMIT 1"),{"u":u["id"],"a":req.ad_id,"s":int(ad["cooldown_seconds"])}).scalar()
            if recent: raise HTTPException(400,"Реклама пока недоступна")
            db.execute(text("INSERT INTO ad_claims(user_id,ad_id) VALUES(:u,:a)"),{"u":u["id"],"a":req.ad_id})
            db.execute(text("UPDATE users SET coins=coins+:r WHERE id=:u"),{"r":ad["reward"],"u":u["id"]})
            db.execute(text("INSERT INTO economy_transactions(user_id,kind,amount,meta) VALUES(:u,'AD_REWARD',:r,:m)"),{"u":u["id"],"r":ad["reward"],"m":str(req.ad_id)})
    except HTTPException: db.rollback(); raise
    return {"ok":True,"reward":int(ad["reward"]) }

@app.get("/api/admin/ads")
def admin_ads(x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    require_admin(db,x_telegram_init_data)
    return {"ads":[dict(r) for r in db.execute(text("SELECT * FROM ad_campaigns ORDER BY id DESC")).mappings()]}

@app.post("/api/admin/ads")
def admin_create_ad(req: AdReq,x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    a=require_admin(db,x_telegram_init_data)
    row=db.execute(text("INSERT INTO ad_campaigns(title,description,reward,url,daily_limit,cooldown_seconds,active) VALUES(:t,:d,:r,:u,:l,:c,:a) RETURNING id"),req.model_dump()).scalar_one(); db.commit()
    db.execute(text("INSERT INTO admin_audit(admin_user_id,action,meta) VALUES(:a,'CREATE_AD',:m)"),{"a":a["id"],"m":json.dumps({"id":row})}); db.commit()
    return {"ok":True,"id":row}

@app.get("/api/games")
def games():
    return {"games":[{"code":"neon_reactor","title":"NEON REACTOR","daily_plays":3,"description":"15 секунд на реакцию: лови ядро, собирай комбо и выбивай награду за собственный результат."}]}

@app.post("/api/games/play")
def play_game(req: GameReq,x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    u=current_user(db,x_telegram_init_data); db.commit()
    if req.game_code != "neon_reactor": raise HTTPException(404,"Game not found")
    try:
        with db.begin():
            old=db.execute(text("SELECT result,reward FROM game_plays WHERE user_id=:u AND game_code=:g AND request_id=:r"),{"u":u["id"],"g":req.game_code,"r":req.request_id}).mappings().first()
            if old: return {"ok":True,"result":old["result"],"reward":int(old["reward"]),"idempotent":True}
            limit=3
            count=db.execute(text("SELECT COUNT(*) FROM game_plays WHERE user_id=:u AND game_code=:g AND created_at::date=CURRENT_DATE"),{"u":u["id"],"g":req.game_code}).scalar_one()
            if int(count)>=limit: raise HTTPException(400,"Попытки на сегодня закончились")
            score=max(0,min(100,int(req.score)))
            if score < 20: reward=0; result="REACTOR COLD"
            elif score < 40: reward=100; result="GOOD START"
            elif score < 60: reward=250; result="FAST HANDS"
            elif score < 75: reward=500; result="HOT REACTOR"
            elif score < 90: reward=1000; result="VLDST ELITE"
            else: reward=3000; result="NEON MASTER"
            db.execute(text("INSERT INTO game_plays(user_id,game_code,reward,result,request_id) VALUES(:u,:g,:r,:s,:id)"),{"u":u["id"],"g":req.game_code,"r":reward,"s":result,"id":req.request_id})
            if reward: db.execute(text("UPDATE users SET coins=coins+:r WHERE id=:u"),{"r":reward,"u":u["id"]})
    except HTTPException: db.rollback(); raise
    return {"ok":True,"result":result,"reward":reward,"score":score}

@app.get("/api/admin/stars")
def admin_stars(x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    require_admin(db,x_telegram_init_data)
    stats=db.execute(text("SELECT COUNT(*) FILTER (WHERE status='PAID') paid_count,COALESCE(SUM(amount) FILTER (WHERE status='PAID'),0) paid_stars,COUNT(*) total FROM payments")).mappings().one()
    return {"stats":dict(stats)}

@app.get("/api/admin/payments")
def admin_payments(x_telegram_init_data: str=Header(...),db: Session=Depends(get_db)):
    require_admin(db,x_telegram_init_data)
    return {"payments":[dict(r) for r in db.execute(text("SELECT p.*,u.telegram_id,u.username FROM payments p JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC LIMIT 100")).mappings()]}


async def bot_loop():
    if not settings.bot_token:
        log.warning("BOT_TOKEN missing; Telegram polling disabled")
        return
    from aiogram import Bot, Dispatcher
    from aiogram.filters import CommandStart
    from aiogram.types import (
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        LabeledPrice,
        Message,
        PreCheckoutQuery,
        WebAppInfo,
    )

    bot = Bot(settings.bot_token)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        arg = (m.text or "").split(maxsplit=1)[1] if (m.text or "").count(" ") else ""
        if arg.startswith("ref_"):
            try:
                ref_id = int(arg[4:])
                with next(get_db()) as db:
                    u = ensure_user(
                        db,
                        {
                            "id": m.from_user.id,
                            "username": m.from_user.username or "",
                            "first_name": m.from_user.first_name or "",
                        },
                    )
                    if int(u["id"]) != ref_id:
                        created = db.execute(
                            text(
                                "INSERT INTO referrals(referrer_id,referred_id,active,earned) "
                                "VALUES(:r,:u,TRUE,1000) ON CONFLICT(referred_id) DO NOTHING"
                            ),
                            {"r": ref_id, "u": u["id"]},
                        )
                        if created.rowcount == 1:
                            db.execute(text("UPDATE users SET coins=coins+1000 WHERE id=:r"), {"r": ref_id})
                            db.execute(text("INSERT INTO economy_transactions(user_id,kind,amount,meta) VALUES(:r,'REFERRAL',1000,:m)"), {"r": ref_id, "m": str(u["id"])})
                        db.commit()
            except Exception:
                log.exception("Referral processing failed")

        url = settings.web_app_url.rstrip("/") + "/app/"
        name = (m.from_user.first_name or "Игрок").strip()
        welcome = (
            f"🔥 <b>Добро пожаловать, {name}!</b>\n\n"
            "🎁 <b>VLDST CASE X</b> — открывай кейсы, собирай редкие предметы и прокачивай свой профиль.\n\n"
            "⚡ Внутри тебя ждут:\n"
            "• 🎁 кейсы и коллекция\n"
            "• 🎮 NEON REACTOR — игра на реакцию и комбо\n"
            "• 🔥 Daily, миссии и сезон\n"
            "• ⭐ Telegram Stars и награды\n\n"
            "🚀 <b>Готов начать?</b> Открывай приложение и забирай свой первый дроп!"
        )
        await m.answer(
            welcome,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 ОТКРЫТЬ VLDST", web_app=WebAppInfo(url=url))],
                ]
            ),
        )

    @dp.pre_checkout_query()
    async def pre_checkout(q: PreCheckoutQuery):
        await q.answer(ok=True)

    @dp.message()
    async def payment_message(m: Message):
        sp = m.successful_payment
        if not sp:
            return
        payload = sp.invoice_payload
        if not payload.startswith("shop:"):
            return
        parts = payload.split(":")
        if len(parts) < 3:
            return
        product_id = parts[1]
        try:
            user_id = int(parts[2])
        except ValueError:
            return
        with next(get_db()) as db:
            payment_id = sp.telegram_payment_charge_id
            inserted = db.execute(
                text(
                    "INSERT INTO payments(user_id,payment_id,payload,currency,amount,status) "
                    "VALUES(:u,:p,:pl,:c,:a,'PAID') "
                    "ON CONFLICT(payment_id) DO NOTHING"
                ),
                {
                    "u": user_id,
                    "p": payment_id,
                    "pl": payload,
                    "c": sp.currency,
                    "a": sp.total_amount,
                },
            )
            # Telegram may retry delivery. Fulfil a Stars payment exactly once.
            if inserted.rowcount != 1:
                db.commit()
                return
            coin_rewards = {"coins_50000": 50000, "coins_150000": 150000, "coins_500000": 500000}
            if product_id in coin_rewards:
                db.execute(text("UPDATE users SET coins=coins+:c WHERE id=:u"), {"c": coin_rewards[product_id], "u": user_id})
                db.execute(text("INSERT INTO economy_transactions(user_id,kind,amount,meta) VALUES(:u,'STARS_PURCHASE',:c,:m)"), {"u": user_id, "c": coin_rewards[product_id], "m": product_id})
            elif product_id == "premium":
                db.execute(
                    text("UPDATE users SET premium=TRUE WHERE id=:u"),
                    {"u": user_id},
                )
            elif product_id == "season_pass":
                db.execute(
                    text("UPDATE users SET premium=TRUE,season_pass=TRUE WHERE id=:u"),
                    {"u": user_id},
                )
            elif product_id == "xp_boost":
                db.execute(
                    text(
                        "UPDATE users SET xp_boost_until=GREATEST("
                        "COALESCE(xp_boost_until,NOW()),NOW())+INTERVAL '24 hours' "
                        "WHERE id=:u"
                    ),
                    {"u": user_id},
                )
            db.commit()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def ensure_schema():
    if not engine:
        return
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS premium BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS season_pass BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS xp_boost_until TIMESTAMPTZ",
        """CREATE TABLE IF NOT EXISTS mission_claims(
            user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
            mission_id TEXT NOT NULL,
            reward BIGINT NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id,mission_id)
        )""",
        """CREATE TABLE IF NOT EXISTS achievement_claims(
            user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
            achievement_id TEXT NOT NULL,
            reward BIGINT NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id,achievement_id)
        )""",
        """CREATE TABLE IF NOT EXISTS admin_audit(
            id BIGSERIAL PRIMARY KEY, admin_user_id BIGINT, action TEXT NOT NULL, target_user_id BIGINT, meta JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS ad_campaigns(
            id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', reward BIGINT NOT NULL DEFAULT 0, url TEXT NOT NULL DEFAULT '', daily_limit INT NOT NULL DEFAULT 1, cooldown_seconds INT NOT NULL DEFAULT 86400, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS ad_claims(
            user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, ad_id BIGINT REFERENCES ad_campaigns(id) ON DELETE CASCADE, claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(user_id,ad_id,claimed_at)
        )""",
        """CREATE TABLE IF NOT EXISTS game_plays(
            id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, game_code TEXT NOT NULL, reward BIGINT NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '', request_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(user_id,game_code,request_id)
        )""",
        """CREATE TABLE IF NOT EXISTS season_claims(
            user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
            level INT NOT NULL,
            reward BIGINT NOT NULL,
            premium BOOLEAN NOT NULL DEFAULT FALSE,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id,level,premium)
        )""",
    ]
    statements += [
        "CREATE TABLE IF NOT EXISTS promo_codes(id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, reward_coins BIGINT NOT NULL DEFAULT 0, reward_xp BIGINT NOT NULL DEFAULT 0, reward_premium BOOLEAN NOT NULL DEFAULT FALSE, max_uses INT NOT NULL DEFAULT 1, used_count INT NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT TRUE, expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS promo_redemptions(promo_id BIGINT REFERENCES promo_codes(id) ON DELETE CASCADE, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(promo_id,user_id))",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


@app.on_event("startup")
async def startup():
    ensure_schema()
    if engine:
        with Session(engine) as db:
            seed_v10(db)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
    asyncio.create_task(bot_loop())
