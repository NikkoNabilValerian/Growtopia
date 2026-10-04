"""Module 2: Discord (akun tumbal) -> parse -> ringkas -> upsert ke Supabase.

Pemakaian:
    python pipeline.py                              # susul: semua hari baru sejak scrape terakhir s/d kemarin
    python pipeline.py --date 2026-10-02            # satu hari tertentu
    python pipeline.py --backfill 2023-01-01 2026-10-03   # dari yang TERBARU ke terlama
    python pipeline.py --backfill 2023-01-01 2026-10-03 --oldest-first
    python pipeline.py --backfill 2021-01-01 2026-09-25 --every 45   # tahap kerangka (titik acuan)
    python pipeline.py --date 2023-04-20 --dry-run  # hitung & tampilkan, TANPA menyimpan
    python pipeline.py --date 2023-04-20 --dry-run --anchor-bgl 0.2   # uji dengan perkiraan harga sebenarnya
    python pipeline.py --backfill 2023-01-01 2026-10-03 --force   # proses ulang walau sudah pernah
    python pipeline.py --backfill 2023-01-01 2026-10-03 --max-minutes 330   # berhenti rapi setelah 5,5 jam
    python pipeline.py --date 2026-10-02 --sample 15  # lihat pesan mentah, tanpa menyimpan

Backfill berjalan dari tanggal terbaru ke terlama: satuan harga untuk angka tanpa
satuan ("growscan 2720") ditentukan dari harga tersimpan di hari-hari yang lebih baru,
yang sudah benar, lalu rantai itu menjalar mundur.

Hari yang sudah selesai dicatat di tabel scrape_log, dan otomatis dilewati pada
run berikutnya (kecuali --force). Hari ini (belum lengkap) tidak pernah dicatat.

Environment variables:
    DISCORD_USER_TOKEN     token akun tumbal (simpan di .env / env var, JANGAN di-commit)
    DISCORD_CHANNEL_IDS    id channel, pisahkan dengan koma
    SUPABASE_URL
    SUPABASE_SERVICE_KEY   service_role key (jangan dipakai di frontend)
    TZ_NAME                default Asia/Jakarta
    REQUEST_DELAY          jeda antar request dalam detik, default 0.7

Catatan: aman dihentikan (Ctrl+C) kapan saja. Hari dicatat satu per satu setelah
selesai, jadi run berikutnya melanjutkan dari hari yang belum selesai.
"""
from __future__ import annotations

import argparse
import os
import time as _time
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from supabase import create_client

from offer_parser import (
    TRACKED_ITEMS,
    Offer,
    mentions_tracked,
    parse_message,
    resolve_offers,
    summarize_day,
)

load_dotenv()  # baca scraper/.env kalau ada

API = "https://discord.com/api/v9"
DISCORD_EPOCH_MS = 1_420_070_400_000
TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Jakarta"))
DELAY = float(os.getenv("REQUEST_DELAY", "0.7"))
TABLE = "daily_item_prices"
LOG_TABLE = "scrape_log"
# Anchor dari baris tersimpan yang lebih jauh dari ini (hari) dianggap basi dan diabaikan,
# karena skala harga bisa berubah banyak dalam beberapa tahun.
MAX_ANCHOR_AGE_DAYS = int(os.getenv("MAX_ANCHOR_AGE_DAYS", "120"))


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
                wait = float(r.json().get("retry_after", 5)) + 0.5
                print(f"[rate limit] Discord meminta menunggu {wait:.1f} detik", flush=True)
                _time.sleep(wait)
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


def iter_messages(dc: DiscordClient, channel_ids: list[int], day: date) -> Iterator[dict]:
    start = datetime.combine(day, time.min, tzinfo=TZ)
    end = start + timedelta(days=1)
    for cid in channel_ids:
        for m in dc.messages_between(cid, start, end):
            if m["author"].get("bot") or not m.get("content"):
                continue
            yield m
        _time.sleep(DELAY)


def fetch_day(dc: DiscordClient, channel_ids: list[int], day: date) -> list[Offer]:
    offers: list[Offer] = []
    for m in iter_messages(dc, channel_ids, day):
        offers.extend(parse_message(m["content"], m["author"]["id"]))
    return offers  # data mentah hanya hidup di memori, per hari


def show_sample(dc: DiscordClient, channel_ids: list[int], day: date, limit: int) -> None:
    """Cetak pesan mentah + hasil parsing. Tidak menulis apa pun ke Supabase."""
    shown = 0
    for m in iter_messages(dc, channel_ids, day):
        if not mentions_tracked(m["content"]):
            continue
        print("RAW   :", repr(m["content"]))
        for o in parse_message(m["content"], m["author"]["id"]):
            print(f"PARSED: {o.action} {o.item} = {o.value:g} {o.unit or '(tanpa satuan)'}")
        print("-" * 50)
        shown += 1
        if shown >= limit:
            break
    print(f"{shown} pesan ditampilkan (mode sample, tidak ada yang disimpan)")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def set_github_output(key: str, value) -> None:
    """Kirim nilai ke langkah berikutnya di GitHub Actions (abaikan bila bukan di Actions)."""
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


def today_local() -> date:
    return datetime.now(TZ).date()


def scraped_days(sb, start: date, end: date) -> set[date]:
    """Tanggal dalam [start, end] yang sudah tercatat selesai di scrape_log."""
    done: set[date] = set()
    for offset in range(0, 1_000_000, 1000):
        data = (
            sb.table(LOG_TABLE).select("date")
            .gte("date", start.isoformat()).lte("date", end.isoformat())
            .order("date").range(offset, offset + 999).execute().data
        )
        done.update(date.fromisoformat(r["date"]) for r in data)
        if len(data) < 1000:
            break
    return done


def last_scraped_day(sb) -> date | None:
    data = sb.table(LOG_TABLE).select("date").order("date", desc=True).limit(1).execute().data
    return date.fromisoformat(data[0]["date"]) if data else None


def fetch_anchor(sb, item: str, day: date, side: str) -> float | None:
    """Level harga (dalam WL) dari baris tersimpan terdekat, dipakai untuk menentukan
    satuan angka tanpa satuan.

    side: "later"   = baris terdekat SETELAH day (untuk backfill terbaru -> terlama)
          "earlier" = baris terdekat SEBELUM day (untuk backfill lama -> baru / susul harian)
          "nearest" = mana saja yang lebih dekat
    """
    def nearest(later: bool):
        q = sb.table(TABLE).select("date, median_price").eq("item_name", item)
        q = q.gt("date", day.isoformat()) if later else q.lt("date", day.isoformat())
        r = q.order("date", desc=not later).limit(1).execute().data
        return (date.fromisoformat(r[0]["date"]), float(r[0]["median_price"])) if r else None

    found = []
    if side in ("later", "nearest"):
        found.append(nearest(True))
    if side in ("earlier", "nearest"):
        found.append(nearest(False))
    found = [f for f in found if f and abs((f[0] - day).days) <= MAX_ANCHOR_AGE_DAYS]
    if not found:
        return None
    _, median_bgl = min(found, key=lambda f: abs((f[0] - day).days))
    return median_bgl * 10_000  # BGL -> WL


def get_anchors(sb, day: date, side: str, override_bgl: float | None) -> dict[str, float | None]:
    if override_bgl:  # anchor manual dari --anchor-bgl, berlaku untuk semua item
        return {item: override_bgl * 10_000 for item in TRACKED_ITEMS}
    return {item: fetch_anchor(sb, item, day, side) for item in TRACKED_ITEMS}


def dry_run_day(sb, dc: DiscordClient, channel_ids: list[int], day: date, side: str,
                override_bgl: float | None = None) -> None:
    """Jalankan seluruh perhitungan untuk satu hari dan tampilkan hasilnya, tanpa menyimpan."""
    anchors = get_anchors(sb, day, side, override_bgl)
    offers = fetch_day(dc, channel_ids, day)
    resolved = resolve_offers(offers, anchors)

    print(f"\n=== {day} (DRY RUN, tidak ada yang disimpan) ===")
    for item, a in anchors.items():
        print(f"anchor {item}: " + (f"{a / 10_000:.4g} BGL" if a else "tidak ada (pakai satuan eksplisit / aturan statis)"))
    print("hasil penentuan satuan:", dict(Counter(r.how for r in resolved)))
    dropped = [r.offer for r in resolved if r.price_wl is None][:8]
    if dropped:
        print("contoh yang dibuang:", ", ".join(f"{o.value:g} {o.unit or '(tanpa satuan)'}" for o in dropped))
    rows = summarize_day(offers, day.isoformat(), anchors)
    if not rows:
        print("tidak ada baris yang akan disimpan (postingan valid < 3)")
    for r in rows:
        print(f"{r['item_name']}: gabungan {r['median_price']} | buy {r['buy_median']} | "
              f"sell {r['sell_median']} BGL  ({r['total_volume']} postingan)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--backfill", nargs=2, type=date.fromisoformat, metavar=("FROM", "TO"))
    ap.add_argument("--oldest-first", action="store_true",
                    help="backfill dari terlama ke terbaru (default: terbaru ke terlama)")
    ap.add_argument("--dry-run", action="store_true",
                    help="hitung dan tampilkan hasil per hari tanpa menyimpan apa pun")
    ap.add_argument("--every", type=int, metavar="N",
                    help="hanya proses 1 hari tiap N hari dalam rentang backfill (tahap kerangka untuk "
                         "scraper paralel: menyebar titik acuan harga dulu)")
    ap.add_argument("--anchor-bgl", type=float, metavar="HARGA",
                    help="paksa level harga acuan (dalam BGL) untuk hari yang diproses, mis. 0.27; "
                         "berguna untuk menguji tanggal lama bersama --dry-run")
    ap.add_argument("--force", action="store_true",
                    help="abaikan scrape_log dan proses ulang hari yang sudah pernah di-scrape")
    ap.add_argument("--max-minutes", type=float, metavar="N",
                    help="berhenti dengan rapi setelah N menit; sisa hari dilanjutkan di run berikutnya")
    ap.add_argument("--sample", type=int, metavar="N",
                    help="tampilkan N pesan mentah + hasil parsing, tanpa menyimpan ke Supabase")
    args = ap.parse_args()

    today = today_local()
    yesterday = today - timedelta(days=1)

    dc = DiscordClient(os.environ["DISCORD_USER_TOKEN"])
    channel_ids = [int(c) for c in os.environ["DISCORD_CHANNEL_IDS"].split(",")]

    if args.sample:
        day = args.date or (args.backfill[0] if args.backfill else yesterday)
        show_sample(dc, channel_ids, day, args.sample)
        return

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    if args.backfill:
        days = list(daterange(*args.backfill))
        if args.oldest_first:
            side = "earlier"
        else:
            days.reverse()
            side = "later"
        if args.every and args.every > 1:
            days = days[::args.every]  # dihitung dari ujung rentang yang diproses lebih dulu
    elif args.date:
        days, side = [args.date], "later"
    else:  # mode susul: lanjut dari hari setelah scrape terakhir sampai kemarin
        last = last_scraped_day(sb)
        days = list(daterange(last + timedelta(days=1) if last else yesterday, yesterday))
        side = "earlier"

    if args.dry_run:
        for day in days:
            dry_run_day(sb, dc, channel_ids, day, side, args.anchor_bgl)
        return

    if not args.force:
        partial = [d for d in days if d >= today]
        if partial:
            print(f"Dilewati {len(partial)} hari yang belum lengkap (hari ini/masa depan). Pakai --force untuk memaksa.")
            days = [d for d in days if d < today]
        if days:
            done = scraped_days(sb, min(days), max(days))
            if done:
                print(f"Dilewati {len(done)} hari yang sudah pernah di-scrape (pakai --force untuk mengulang).")
            days = [d for d in days if d not in done]

    if not days:
        print("Tidak ada hari baru untuk diproses.")
        set_github_output("remaining", 0)
        return
    print(f"Memproses {len(days)} hari: {days[0]} lalu {days[-1]} (urutan {'terlama' if days[0] < days[-1] else 'terbaru'} dulu)", flush=True)

    started = _time.monotonic()
    remaining = 0
    for i, day in enumerate(days):
        if args.max_minutes and (_time.monotonic() - started) / 60 >= args.max_minutes:
            remaining = len(days) - i
            print(f"Batas waktu {args.max_minutes:g} menit tercapai. "
                  f"Sisa {remaining} hari, lanjut di run berikutnya.", flush=True)
            break
        anchors = get_anchors(sb, day, side, args.anchor_bgl)
        offers = fetch_day(dc, channel_ids, day)
        rows = summarize_day(offers, day.isoformat(), anchors)
        if rows:
            sb.table(TABLE).upsert(rows, on_conflict="item_name,date").execute()
        # Hapus baris lama item yang kini tidak punya data valid hari itu (mis. hasil
        # parsing versi lama yang salah), supaya tidak tertinggal di chart.
        have = {r["item_name"] for r in rows}
        for item in TRACKED_ITEMS:
            if item not in have:
                sb.table(TABLE).delete().eq("item_name", item).eq("date", day.isoformat()).execute()
        if day < today:  # hari yang belum selesai tidak dicatat, supaya diulang besok
            sb.table(LOG_TABLE).upsert(
                {"date": day.isoformat(), "offers": len(offers)}, on_conflict="date"
            ).execute()
        print(f"{day}: {len(offers)} penawaran -> {len(rows)} baris tersimpan", flush=True)
    set_github_output("remaining", remaining)


if __name__ == "__main__":
    main()