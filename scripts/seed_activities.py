"""Seed demo activity data into the configured PostgreSQL database.

Usage:
    python -m scripts.seed_activities
    python scripts/seed_activities.py
    python scripts/seed_activities.py --reset-demo
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import get_db_connection, initialize_tables  # noqa: E402

TZ = ZoneInfo("Asia/Taipei")
DEMO_PREFIX = "【示範】"


def at(base: datetime, days: int = 0, hour: int = 10, minute: int = 0) -> datetime:
    target = base + timedelta(days=days)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


def build_demo_activities(now: datetime) -> list[dict]:
    """Return demo activities with statuses across the workflow."""
    base = now.astimezone(TZ)
    return [
        {
            "title": f"{DEMO_PREFIX}AI 工具入門工作坊",
            "description": "從實際案例認識生成式 AI 工具，練習用於學習整理、簡報發想與專題腦力激盪的基本流程。",
            "location": "綜合教學大樓 E204 電腦教室",
            "organizer": "資訊素養推廣小組",
            "category": "workshop",
            "capacity": 30,
            "duration": "約 2 小時",
            "starts_at": at(base, 7, 14, 0),
            "ends_at": at(base, 7, 16, 0),
            "registration_opens_at": at(base, -1, 9, 0),
            "registration_deadline": at(base, 6, 23, 59),
            "status": "published",
            "review_note": None,
            "published_at": at(base, -1, 9, 5),
        },
        {
            "title": f"{DEMO_PREFIX}校園永續生活分享會",
            "description": "邀請師生分享減塑、循環利用與低碳通勤的日常實踐，交流可在校園落地的永續想法。",
            "location": "圖書館一樓多功能展演區",
            "organizer": "永續發展辦公室",
            "category": "talk",
            "capacity": 80,
            "duration": "約 90 分鐘",
            "starts_at": at(base, 10, 12, 10),
            "ends_at": at(base, 10, 13, 40),
            "registration_opens_at": at(base, 0, 8, 0),
            "registration_deadline": at(base, 9, 18, 0),
            "status": "published",
            "review_note": None,
            "published_at": at(base, 0, 8, 10),
        },
        {
            "title": f"{DEMO_PREFIX}社團幹部交接茶會",
            "description": "提供新舊幹部交流活動規劃與經驗傳承的輕鬆聚會，歡迎各社團成員參加。",
            "location": "學生活動中心 302 會議室",
            "organizer": "課外活動組",
            "category": "club",
            "capacity": 40,
            "duration": "約 2 小時",
            "starts_at": at(base, 14, 18, 30),
            "ends_at": at(base, 14, 20, 30),
            "registration_opens_at": at(base, 1, 9, 0),
            "registration_deadline": at(base, 13, 17, 0),
            "status": "published",
            "review_note": None,
            "published_at": at(base, 1, 9, 15),
        },
        {
            "title": f"{DEMO_PREFIX}期末舒壓夜跑",
            "description": "以輕鬆配速繞行校園路線，完跑後提供補給與伸展引導，適合想放鬆身心的同學。",
            "location": "體育館前廣場集合",
            "organizer": "路跑社",
            "category": "sports",
            "capacity": 60,
            "duration": "約 75 分鐘",
            "starts_at": at(base, 21, 19, 0),
            "ends_at": at(base, 21, 20, 15),
            "registration_opens_at": at(base, 3, 9, 0),
            "registration_deadline": at(base, 20, 12, 0),
            "status": "published",
            "review_note": None,
            "published_at": at(base, 3, 9, 20),
        },
        {
            "title": f"{DEMO_PREFIX}職涯履歷一對一健檢",
            "description": "由職涯顧問提供履歷與自傳回饋，協助參加者整理實習與求職申請重點。",
            "location": "職涯發展中心諮詢室 B",
            "organizer": "職涯發展中心",
            "category": "career",
            "capacity": 12,
            "duration": "每人 20 分鐘（分時段）",
            "starts_at": at(base, 5, 13, 0),
            "ends_at": at(base, 5, 17, 0),
            "registration_opens_at": at(base, -7, 9, 0),
            "registration_deadline": at(base, 4, 17, 0),
            "status": "approved",
            "review_note": "內容與場地已確認，可排程發布。",
            "published_at": None,
        },
        {
            "title": f"{DEMO_PREFIX}手機攝影構圖練習",
            "description": "帶領同學以校園場景練習主題、光線與構圖，建立日常影像記錄的觀察方法。",
            "location": "人文學院中庭",
            "organizer": "攝影社",
            "category": "culture",
            "capacity": 25,
            "duration": "約 2 小時",
            "starts_at": at(base, 12, 15, 30),
            "ends_at": at(base, 12, 17, 30),
            "registration_opens_at": at(base, 2, 9, 0),
            "registration_deadline": at(base, 11, 12, 0),
            "status": "draft",
            "review_note": None,
            "published_at": None,
        },
        {
            "title": f"{DEMO_PREFIX}桌遊新手同樂夜（需補件）",
            "description": "透過破冰桌遊認識新朋友，活動包含規則說明與分組對戰。",
            "location": "學生餐廳二樓交誼空間",
            "organizer": "桌遊社",
            "category": "club",
            "capacity": 20,
            "duration": "約 2.5 小時",
            "starts_at": at(base, 18, 18, 0),
            "ends_at": at(base, 18, 20, 30),
            "registration_opens_at": at(base, 5, 9, 0),
            "registration_deadline": at(base, 17, 18, 0),
            "status": "rejected",
            "review_note": "請補充活動安全說明與工作人員配置後重新送審。",
            "published_at": None,
        },
        {
            "title": f"{DEMO_PREFIX}秋季校園導覽走讀（已封存）",
            "description": "帶領參加者認識校園歷史建築與自然景點，回顧本學期走讀活動紀錄。",
            "location": "行政大樓前集合",
            "organizer": "導覽服務隊",
            "category": "other",
            "capacity": 35,
            "duration": "約 90 分鐘",
            "starts_at": at(base, -20, 10, 0),
            "ends_at": at(base, -20, 11, 30),
            "registration_opens_at": at(base, -35, 9, 0),
            "registration_deadline": at(base, -21, 18, 0),
            "status": "archived",
            "review_note": None,
            "published_at": at(base, -35, 9, 30),
        },
    ]


INSERT_SQL = """
    INSERT INTO activities (
        title, description, location, organizer, category, capacity, duration,
        starts_at, ends_at, registration_opens_at, registration_deadline,
        status, review_note, created_by, published_at
    )
    VALUES (
        %(title)s, %(description)s, %(location)s, %(organizer)s, %(category)s,
        %(capacity)s, %(duration)s, %(starts_at)s, %(ends_at)s,
        %(registration_opens_at)s, %(registration_deadline)s,
        %(status)s, %(review_note)s, %(created_by)s, %(published_at)s
    )
    RETURNING id, title, status
"""


def reset_demo(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM activities WHERE title LIKE %s RETURNING id",
            (f"{DEMO_PREFIX}%",),
        )
        deleted = len(cur.fetchall())
    conn.commit()
    return deleted


def seed_demo(conn, activities: list[dict]) -> list[tuple]:
    created = []
    with conn.cursor() as cur:
        for activity in activities:
            cur.execute(INSERT_SQL, {**activity, "created_by": None})
            created.append(cur.fetchone())
    conn.commit()
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo activity data.")
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help=f"Delete existing activities whose title starts with {DEMO_PREFIX!r} before seeding.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    try:
        with get_db_connection() as conn:
            initialize_tables(conn)
            if args.reset_demo:
                deleted = reset_demo(conn)
                print(f"Removed {deleted} existing demo activities.")
            created = seed_demo(conn, build_demo_activities(datetime.now(TZ)))
    except Exception as exc:  # pragma: no cover - CLI feedback
        print(f"Seeding failed: {exc}", file=sys.stderr)
        print(
            "Check that DATABASE_URL is set and PostgreSQL is reachable.",
            file=sys.stderr,
        )
        return 1

    print(f"Inserted {len(created)} demo activities:")
    for activity_id, title, status in created:
        print(f"- #{activity_id} [{status}] {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
