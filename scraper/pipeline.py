"""Module 2: Discord (akun tumbal) -> parse -> ringkas -> upsert ke Supabase.

Pemakaian:
    python pipeline.py                              # kemarin (mode harian)
    python pipeline.py --date 2026-10-02            # satu hari tertentu
    python pipeline.py --backfill 2023-01-01 2026-10-03

Environment variables:
    DISCORD_USER_TOKEN     token akun tumbal (simpan di .env / env var, JANGAN di-commit)
    DISCORD_CHANNEL_IDS    id channel, pisahkan dengan koma
    SUPABASE_URL
    SUPABASE_SERVICE_KEY   service_role key (jangan dipakai di frontend)
    TZ_NAME                default Asia/Jakarta
    REQUEST_DELAY          jeda antar request dalam detik, default 0.7

Catatan: script ini idempoten (upsert), jadi aman dijalankan ulang untuk
rentang tanggal yang sama kalau backfill terputus di tengah jalan.
"""
from __future__ import annotations

import argparse
import os
import time as _time
from datetime import date, datetime, time, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from supabase import create_client

from offer_parser import Offer, parse_message, summarize_day

load_dotenv()  # baca scraper/.env kalau ada

API = "https://discord.com/api/v9"
DISCORD_EPOCH_MS = 1_420_070_400_000
TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Jakarta"))
DELAY = float(os.getenv("REQUEST_DELAY", "0.7"))
TABLE = "daily_item_prices"


def to_snowflake(dt: datetime) -> int:
    """Discord ID memuat timestamp, jadi batas waktu bisa dipakai sebagai cursor."""
    return (int(dt.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22


class DiscordClient:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers["Authorization"] = token

    def _get(self, path: str, params: dict):
        for _ in range(8):
            r = self.s.get(f"{API}{path}", params=params, timeout=30)
            if r.status_code == 429:  # kena rate limit: tunggu sesuai arahan Discord
                _time.sleep(float(r.json().get("retry_after", 5)) + 0.5)
                continue
            if r.status_code in (401, 403):
                raise SystemExit(
                    f"Discord menolak akses ({r.status_code}). Cek token, atau akun "
                    f"tidak punya izin baca channel {path}."
                )
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Terlalu banyak retry untuk {path}")

    def messages_between(self, channel_id: int, start: datetime, end: datetime) -> Iterator[dict]:
        """Ambil pesan [start, end) dengan paginasi mundur (terbaru -> terlama)."""
        lo = to_snowflake(start)
        before = to_snowflake(end)
        while True:
            batch = self._get(
                f"/channels/{channel_id}/messages", {"limit": 100, "before": before}
            )
            if not batch:
                return
            for m in batch:
                if int(m["id"]) < lo:
                    return
                yield m
            before = batch[-1]["id"]
            _time.sleep(DELAY)


def fetch_day(dc: DiscordClient, channel_ids: list[int], day: date) -> list[Offer]:
    start = datetime.combine(day, time.min, tzinfo=TZ)
    end = start + timedelta(days=1)
    offers: list[Offer] = []
    for cid in channel_ids:
        for m in dc.messages_between(cid, start, end):
            if m["author"].get("bot") or not m.get("content"):
                continue
            offers.extend(parse_message(m["content"], m["author"]["id"]))
        _time.sleep(DELAY)
    return offers  # data mentah hanya hidup di memori, per hari


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--backfill", nargs=2, type=date.fromisoformat, metavar=("FROM", "TO"))
    args = ap.parse_args()

    if args.backfill:
        days = list(daterange(*args.backfill))
    elif args.date:
        days = [args.date]
    else:
        days = [datetime.now(TZ).date() - timedelta(days=1)]  # hari yang sudah lengkap

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    dc = DiscordClient(os.environ["DISCORD_USER_TOKEN"])
    channel_ids = [int(c) for c in os.environ["DISCORD_CHANNEL_IDS"].split(",")]

    for day in days:
        offers = fetch_day(dc, channel_ids, day)
        rows = summarize_day(offers, day.isoformat())
        if rows:
            sb.table(TABLE).upsert(rows, on_conflict="item_name,date").execute()
        print(f"{day}: {len(offers)} penawaran -> {len(rows)} baris tersimpan", flush=True)


if __name__ == "__main__":
    main()