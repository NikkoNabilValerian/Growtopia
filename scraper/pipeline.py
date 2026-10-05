"""Module 2: Discord (akun tumbal) -> parse -> ringkas -> upsert ke Supabase.

Item yang dipantau dikonfigurasi di items.py. Satu kali membaca pesan Discord melayani
SEMUA item, jadi menambah item hampir tidak menambah waktu scrape.

Pemakaian:
    python pipeline.py                              # susul: semua hari baru s/d kemarin
    python pipeline.py --date 2026-10-02            # satu hari tertentu
    python pipeline.py --backfill 2023-01-01 2026-10-03   # dari yang TERBARU ke terlama
    python pipeline.py --backfill 2023-01-01 2026-10-03 --oldest-first
    python pipeline.py --backfill 2021-01-01 2026-09-25 --every 45   # tahap kerangka (titik acuan)
    python pipeline.py --backfill ... --items magplant,growscan      # hanya item tertentu
    python pipeline.py --date 2023-04-20 --dry-run  # hitung & tampilkan, TANPA menyimpan
    python pipeline.py --date 2023-04-20 --dry-run --anchor-bgl 0.2   # uji dengan perkiraan harga sebenarnya
    python pipeline.py --backfill 2023-01-01 2026-10-03 --force   # proses ulang walau sudah pernah
    python pipeline.py --backfill 2023-01-01 2026-10-03 --max-minutes 330   # berhenti rapi setelah 5,5 jam
    python pipeline.py --date 2026-10-02 --sample 15  # lihat pesan mentah, tanpa menyimpan

Backfill berjalan dari tanggal terbaru ke terlama: satuan harga untuk angka tanpa
satuan ("growscan 2720") ditentukan dari harga tersimpan di hari-hari yang lebih baru,
yang sudah benar, lalu rantai itu menjalar mundur.

Hari yang sudah selesai dicatat PER ITEM di tabel scrape_log dan otomatis dilewati pada
run berikutnya (kecuali --force). Hari ini (belum lengkap) tidak pernah dicatat.

Environment variables:
    DISCORD_USER_TOKEN     token akun tumbal (simpan di .env / env var, JANGAN di-commit)
    DISCORD_CHANNEL_IDS    id channel, pisahkan dengan koma
    SUPABASE_URL
    SUPABASE_SERVICE_KEY   secret key (jangan dipakai di frontend)
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

from items import ITEMS
from offer_parser import (
    ITEM_LABELS,
    SIDE_BAND,
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
MAX_TRANSIENT_FAILURES = 8   # ~10 menit total menunggu sebelum satu hari dilewati sementara
# Anchor dari baris tersimpan yang lebih jauh dari ini (hari) dianggap basi dan diabaikan,
# karena skala harga bisa berubah banyak dalam beberapa tahun.
MAX_ANCHOR_AGE_DAYS = int(os.getenv("MAX_ANCHOR_AGE_DAYS", "120"))


def to_snowflake(dt: datetime) -> int:
    """Discord ID memuat timestamp, jadi batas waktu bisa dipakai sebagai cursor."""
    return (int(dt.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22


class TransientError(Exception):
    """Gangguan sementara dari Discord (5xx / jaringan) yang tidak pulih setelah beberapa kali coba."""


class DiscordClient:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers["Authorization"] = token

    def _get(self, path: str, params: dict):
        """GET dengan retry: rate limit (429) menunggu sesuai arahan Discord; error server
        (5xx) dan gangguan jaringan diulang dengan jeda yang makin lama."""
        failures = 0
        for _ in range(500):
            try:
                r = self.s.get(f"{API}{path}", params=params, timeout=30)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                failures += 1
                wait = min(60, 5 * failures)
                print(f"[jaringan] {type(e).__name__}, coba lagi dalam {wait} detik "
                      f"(gagal ke-{failures})", flush=True)
            else:
                if r.status_code == 429:  # rate limit: tunggu sesuai arahan Discord
                    wait = float(r.json().get("retry_after", 5)) + 0.5
                    print(f"[rate limit] Discord meminta menunggu {wait:.1f} detik", flush=True)
                    _time.sleep(wait)
                    continue
                if r.status_code in (401, 403):
                    raise SystemExit(
                        f"Discord menolak akses ({r.status_code}). Cek token, atau akun "
                        f"tidak punya izin baca channel {path}."
                    )
                if r.status_code < 500:
                    r.raise_for_status()  # 4xx lain = masalah permanen, jangan diulang
                    return r.json()
                failures += 1
                wait = min(120, 5 * 2 ** min(failures, 5))
                print(f"[server] Discord membalas {r.status_code}, coba lagi dalam {wait} detik "
                      f"(gagal ke-{failures})", flush=True)
            if failures > MAX_TRANSIENT_FAILURES:
                raise TransientError(f"Discord tidak stabil untuk {path} setelah {failures} percobaan")
            _time.sleep(wait)
        raise TransientError(f"Terlalu banyak retry untuk {path}")

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


# ----------------------------------------------------------- scrape_log per item

def logged_days(sb, items: list[str], start: date, end: date) -> dict[str, set[date]]:
    """Tanggal dalam [start, end] yang sudah selesai, per item."""
    done: dict[str, set[date]] = {i: set() for i in items}
    for item in items:
        for offset in range(0, 1_000_000, 1000):
            data = (
                sb.table(LOG_TABLE).select("date").eq("item_name", item)
                .gte("date", start.isoformat()).lte("date", end.isoformat())
                .order("date").range(offset, offset + 999).execute().data
            )
            done[item].update(date.fromisoformat(r["date"]) for r in data)
            if len(data) < 1000:
                break
    return done


def last_logged_day(sb, item: str) -> date | None:
    data = (sb.table(LOG_TABLE).select("date").eq("item_name", item)
            .order("date", desc=True).limit(1).execute().data)
    return date.fromisoformat(data[0]["date"]) if data else None


def item_has_rows(sb, item: str) -> bool:
    return bool(sb.table(TABLE).select("date").eq("item_name", item).limit(1).execute().data)


def sync_items(sb, items: list[str]) -> None:
    """Salin label item dari items.py ke tabel items agar website bisa menampilkannya."""
    try:
        rows = [{"item_name": n, "label": ITEM_LABELS[n], "sort_order": i}
                for i, n in enumerate(ITEMS) if n in items]
        sb.table("items").upsert(rows, on_conflict="item_name").execute()
    except Exception as e:  # tabel belum dimigrasi: jangan hentikan scrape
        print(f"[peringatan] sinkronisasi tabel items dilewati ({type(e).__name__}).", flush=True)


# ------------------------------------------------------------------- anchor

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


def make_seeds(sb, items: list[str]) -> dict[str, float]:
    """Patokan awal (WL) dari items.py, hanya untuk item yang belum punya data sama sekali."""
    return {
        i: ITEMS[i]["seed_anchor_bgl"] * 10_000
        for i in items
        if ITEMS[i].get("seed_anchor_bgl") and not item_has_rows(sb, i)
    }


def get_anchors(sb, items: list[str], day: date, side: str, override_bgl: float | None,
                seeds: dict[str, float]) -> dict[str, float | None]:
    if override_bgl:  # anchor manual dari --anchor-bgl, berlaku untuk semua item
        return {i: override_bgl * 10_000 for i in items}
    return {i: fetch_anchor(sb, i, day, side) or seeds.get(i) for i in items}


def dry_run_day(sb, dc: DiscordClient, channel_ids: list[int], day: date, side: str,
                items: list[str], override_bgl: float | None, seeds: dict[str, float]) -> None:
    """Jalankan seluruh perhitungan untuk satu hari dan tampilkan hasilnya, tanpa menyimpan."""
    anchors = get_anchors(sb, items, day, side, override_bgl, seeds)
    offers = [o for o in fetch_day(dc, channel_ids, day) if o.item in items]
    resolved = resolve_offers(offers, anchors)

    print(f"\n=== {day} (DRY RUN, tidak ada yang disimpan) ===")
    for item in items:
        a = anchors.get(item)
        print(f"[{item}] anchor: " + (f"{a / 10_000:.4g} BGL" if a else "tidak ada (pakai satuan eksplisit / aturan statis)"))
        mine = [r for r in resolved if r.offer.item == item]
        print(f"[{item}] hasil penentuan satuan:", dict(Counter(r.how for r in mine)))
        dropped = [r.offer for r in mine if r.price_wl is None][:8]
        if dropped:
            print(f"[{item}] contoh yang dibuang:", ", ".join(f"{o.value:g} {o.unit or '(tanpa satuan)'}" for o in dropped))
    rows = summarize_day(offers, day.isoformat(), anchors)
    if not rows:
        print("tidak ada baris yang akan disimpan (postingan valid < 3)")
    for r in rows:
        print(f"[{r['item_name']}] gabungan {r['median_price']} | buy {r['buy_median']} (dari {r['buy_volume']} post) | "
              f"sell {r['sell_median']} (dari {r['sell_volume']} post) | 1-suara-per-penulis {r['author_median']} BGL  "
              f"({r['total_volume']} postingan, {r['total_authors']} penulis)")

    # Diagnosis: pesan mentah yang harganya jauh dari median hari itu atau dibuang.
    centers = {r["item_name"]: r["median_price"] for r in rows}
    far = []
    for r in resolved:
        c = centers.get(r.offer.item)
        if r.price_wl is None:
            far.append((r, "DIBUANG (jauh dari patokan)"))
        elif c and not (c / SIDE_BAND <= r.price_wl / 10_000 <= c * SIDE_BAND):
            far.append((r, f"jauh dari median {c:.4g} BGL"))
    if far:
        print(f"\nPesan yang harganya mencurigakan ({len(far)} total, maks. 15 ditampilkan):")
        for r, why in far[:15]:
            o = r.offer
            price = "-" if r.price_wl is None else f"{r.price_wl / 10_000:.4g} BGL"
            print(f"  [{o.item}] {o.action:4} terbaca {price:>10} ({r.how}) | {why}\n         pesan: {o.raw!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--backfill", nargs=2, type=date.fromisoformat, metavar=("FROM", "TO"))
    ap.add_argument("--items", help="daftar item dipisah koma (default: semua item di items.py)")
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

    items = list(ITEMS)
    if args.items:
        items = [i.strip() for i in args.items.split(",") if i.strip()]
        unknown = [i for i in items if i not in ITEMS]
        if unknown:
            raise SystemExit(f"Item tidak dikenal: {unknown}. Item yang ada di items.py: {list(ITEMS)}")

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
        lasts = [d for d in (last_logged_day(sb, i) for i in items) if d]
        days = list(daterange(min(lasts) + timedelta(days=1) if lasts else yesterday, yesterday))
        side = "earlier"

    seeds = make_seeds(sb, items)

    if args.dry_run:
        for day in days:
            dry_run_day(sb, dc, channel_ids, day, side, items, args.anchor_bgl, seeds)
        return

    # pending[hari] = item yang belum selesai di hari itu
    if args.force:
        pending = {d: list(items) for d in days}
    else:
        partial = [d for d in days if d >= today]
        if partial:
            print(f"Dilewati {len(partial)} hari yang belum lengkap (hari ini/masa depan). Pakai --force untuk memaksa.")
            days = [d for d in days if d < today]
        pending = {d: list(items) for d in days}
        if days:
            done = logged_days(sb, items, min(days), max(days))
            pending = {d: [i for i in items if d not in done[i]] for d in days}
            skipped = sum(1 for d in days if not pending[d])
            if skipped:
                print(f"Dilewati {skipped} hari yang sudah selesai untuk semua item (pakai --force untuk mengulang).")
            days = [d for d in days if pending[d]]

    if not days:
        print("Tidak ada hari baru untuk diproses.")
        set_github_output("remaining", 0)
        return
    sync_items(sb, items)
    print(f"Memproses {len(days)} hari: {days[0]} lalu {days[-1]} "
          f"(urutan {'terlama' if days[0] < days[-1] else 'terbaru'} dulu), item: {', '.join(items)}", flush=True)

    started = _time.monotonic()
    remaining = 0
    failed = 0
    succeeded = 0
    for i, day in enumerate(days):
        if args.max_minutes and (_time.monotonic() - started) / 60 >= args.max_minutes:
            remaining = len(days) - i
            print(f"Batas waktu {args.max_minutes:g} menit tercapai. "
                  f"Sisa {remaining} hari, lanjut di run berikutnya.", flush=True)
            break
        todo = pending[day]
        anchors = get_anchors(sb, todo, day, side, args.anchor_bgl, seeds)
        try:
            all_offers = fetch_day(dc, channel_ids, day)
        except TransientError as e:
            failed += 1
            print(f"{day}: GAGAL sementara ({e}). Dilewati, akan dicoba lagi di run berikutnya.", flush=True)
            continue
        offers = [o for o in all_offers if o.item in todo]
        rows = summarize_day(offers, day.isoformat(), anchors)
        if rows:
            sb.table(TABLE).upsert(rows, on_conflict="item_name,date").execute()
        # Hapus baris lama item yang kini tidak punya data valid hari itu (mis. hasil
        # parsing versi lama yang salah), supaya tidak tertinggal di chart.
        have = {r["item_name"] for r in rows}
        for item in todo:
            if item not in have:
                sb.table(TABLE).delete().eq("item_name", item).eq("date", day.isoformat()).execute()
        counts = Counter(o.item for o in offers)
        if day < today:  # hari yang belum selesai tidak dicatat, supaya diulang besok
            sb.table(LOG_TABLE).upsert(
                [{"item_name": item, "date": day.isoformat(), "offers": counts.get(item, 0)} for item in todo],
                on_conflict="item_name,date",
            ).execute()
        succeeded += 1
        summary = ", ".join(f"{item}: {counts.get(item, 0)} -> {'1' if item in have else '0'} baris" for item in todo)
        print(f"{day}: {summary}", flush=True)

    if failed and not succeeded:
        # Tidak ada kemajuan sama sekali: jangan memicu run lanjutan (bisa berputar tanpa henti).
        raise SystemExit(f"{failed} hari gagal dan tidak ada yang berhasil. Discord mungkin sedang bermasalah; coba lagi nanti.")
    if failed:
        print(f"{failed} hari gagal sementara dan akan dicoba lagi di run berikutnya.", flush=True)
    set_github_output("remaining", remaining + failed)


if __name__ == "__main__":
    main()