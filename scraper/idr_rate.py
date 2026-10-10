"""Kurs DL/BGL -> rupiah per hari, dari channel Discord jual-beli DL (token & klien sama dengan pipeline.py).

    python idr_rate.py --date 2026-02-10 --sample 40      # lihat bacaan mentah (tanpa menyimpan)
    python idr_rate.py --date 2026-02-10 --dry-run        # hitung & tampilkan (tanpa menyimpan)
    python idr_rate.py --backfill 2023-10-01 2026-10-09   # simpan ke Supabase (bisa dihentikan & dilanjutkan)

Channel bawaan: 1083704905035952210 (ubah dengan --channels atau env IDR_CHANNEL_IDS).

Yang dibaca: pesan para pengepul, mis. "BUY DL 850 | BGL 85.000 / SELL DL 880 | BGL 88.000".
BUY/SELL adalah harga dari sisi pengepul (bid/ask). Nilai harian `idr_per_dl` = titik tengah median BUY dan
median SELL, supaya tidak ikut naik-turun hanya karena jumlah postingan BUY vs SELL berbeda.
Semua harga dinormalkan ke "rupiah per 1 DL" (1 BGL = 100 DL). Hari tanpa >= 3 postingan di kedua sisi dilewati.

SQL (jalankan sekali di Supabase):
    create table if not exists daily_idr_rates (
        date date primary key,
        idr_per_dl numeric(14,2) not null,      -- titik tengah (buy+sell)/2, rupiah per 1 DL
        buy_idr_per_dl numeric(14,2) not null,
        sell_idr_per_dl numeric(14,2) not null,
        idr_per_dl_from_dl numeric(14,2),       -- hanya dari postingan satuan DL
        idr_per_dl_from_bgl numeric(14,2),      -- hanya dari postingan satuan BGL (harga BGL / 100)
        posts int not null,
        authors int not null
    );
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from statistics import median, quantiles

DEFAULT_CHANNELS = "1083704905035952210"
EMOJI_ID_UNITS = {"1083907791523164302": "bgl", "1083731540732805131": "dl"}   # :bgl: dan :DL: di server ini
DL_PER_UNIT = {"dl": 1, "bgl": 100}
MIN_SIDE_POSTS = 3      # satu sisi (buy/sell) butuh minimal ini agar hari itu disimpan
BAND = 2.0              # postingan di luar [median/2, median*2] dibuang
PAIR_RATIO = (80, 125)  # tanpa satuan: dua angka dengan rasio ~100 = (DL, BGL)

EMOJI_RE = re.compile(r"<a?:([\w~]+):(\d+)>|:([\w~]+):")
UNIT_RE = re.compile(r"(?<![a-z])(bgl|dl|diamond\s*lock|blue\s*gem\s*lock)s?(?![a-z0-9])", re.I)
ACTION_RE = re.compile(r"(?<![a-z0-9])(sell|selling|wts|jual|buy|buyy|buying|wtb|beli)(?![a-z0-9])", re.I)
SELL_WORDS = {"sell", "selling", "wts", "jual"}
PER_RE = re.compile(r"(?:/|=|@|\brate\b|\bper\b|\beach\b|\bea\b|\bsatuan\b)", re.I)
NUM_RE = re.compile(r"(?<![\w.,])(?P<rp>rp\.?\s*|idr\s*)?(?P<num>\d+(?:[.,]\d+)*)\s*(?P<suf>k|rb|ribu|jt|juta)?(?![a-z0-9])", re.I)
GROUPED_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
MIN_BEFORE_RE = re.compile(r"(?:min(?:imal|imum)?|need|needs|qty|butuh|stock)\W*$", re.I)
QTY_BEFORE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*$")
UNIT_BEFORE_RE = re.compile(r"(?:bgl|dl)s?[\W_]*(?:rp\.?|idr)?\s*$", re.I)
QTY_AFTER_RE = re.compile(r"\s*(?:pcs?|pieces?|biji|buah|units?|items?|hari|days?|jam|hours?)(?![a-z])", re.I)
SUFFIX_MULT = {"k": 1e3, "rb": 1e3, "ribu": 1e3, "jt": 1e6, "juta": 1e6}


def _emoji_sub(m: re.Match) -> str:
    name = (m[1] or m[3]).lower()
    unit = EMOJI_ID_UNITS.get(m[2] or "")
    if unit is None:   # nama emoji bervariasi: shinydl, dlshinetnk, andrianDLS, bgl~3, AndrianBGL, ...
        unit = "bgl" if "bgl" in name else ("dl" if "dl" in name else None)
    return f" {unit} " if unit else " "


def _unit(raw: str) -> str:
    return "bgl" if re.sub(r"\s+", "", raw.lower()) in ("bgl", "bluegemlock") else "dl"


def _num_value(m: re.Match) -> float | None:
    s, suf = m["num"], (m["suf"] or "").lower()
    try:
        if suf:
            return float(s.replace(",", ".")) * SUFFIX_MULT[suf]
        if GROUPED_RE.fullmatch(s):
            return float(re.sub(r"[.,]", "", s))
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _candidates(line: str) -> list[tuple[int, float]]:
    """Angka yang mungkin harga rupiah: bukan jumlah minimal/dibutuhkan, bukan dolar, bukan jumlah barang."""
    out = []
    for m in NUM_RE.finditer(line):
        before, after = line[: m.start()], line[m.end():]
        if MIN_BEFORE_RE.search(before) or re.match(r"\s*\$", after) or re.search(r"\$\s*$", before):
            continue
        # angka + satuan = jumlah ('5 bgl'), kecuali angka itu harga satuan sebelumnya ('dl 850 bgl 85.000')
        if (UNIT_RE.match(after.lstrip()) and not UNIT_BEFORE_RE.search(before)) or QTY_AFTER_RE.match(after):
            continue
        v = _num_value(m)
        if v and v > 0:
            out.append((m.start(), v))
    return out


def _units(line: str) -> list[dict]:
    """Sebutan satuan: plain (harga mengikuti), qty ('5 bgl' = jumlah), min ('min 10 dl' = diabaikan)."""
    res = []
    for u in UNIT_RE.finditer(line):
        pre = line[: u.start()]
        kind, qty = "plain", None
        q = QTY_BEFORE_RE.search(pre)
        if q and not UNIT_BEFORE_RE.search(pre[: q.start()]):   # 'dl 850 bgl ...': 850 = harga dl, bukan jumlah bgl
            if MIN_BEFORE_RE.search(pre[: q.start()]):
                kind = "min"
            else:
                kind, qty = "qty", float(q[1].replace(",", "."))
        res.append({"start": u.start(), "end": u.end(), "unit": _unit(u[1]), "kind": kind, "qty": qty})
    return res


def _read_line(line: str) -> list[tuple[str, float]]:
    """-> [(unit, idr_per_dl)] untuk satu baris."""
    cands = _candidates(line)
    if not cands:
        return []
    units = _units(line)
    plain = [u for u in units if u["kind"] == "plain"]
    merged = []
    for u in plain:   # ':bgl: BGL 30.000' = satu sebutan
        if merged and merged[-1]["unit"] == u["unit"] and not re.search(r"[a-z0-9]", line[merged[-1]["end"]: u["start"]], re.I):
            continue
        merged.append(u)
    last_pos = cands[-1][0]
    merged = [u for u in merged if u["start"] < last_pos]   # satuan setelah angka terakhir = hiasan
    qtys = [u for u in units if u["kind"] == "qty"]

    if qtys and not merged and len(qtys) == 1 and len(cands) == 1:   # 'sell 5bgl rate 33,5k' / 'wtb 5 bgl 1.3jt'
        u, price = qtys[0], cands[0][1]
        if not PER_RE.search(line):
            price /= u["qty"]
        return [(u["unit"], price / DL_PER_UNIT[u["unit"]])]
    if merged:
        if len(merged) != len(cands):
            return []       # ambigu (mis. 'DL & BGL Rp 300'): lebih baik dilewati daripada salah baca
        return [(u["unit"], v / DL_PER_UNIT[u["unit"]]) for u, (_, v) in zip(merged, cands)]
    if not qtys and len(cands) == 2:   # format tanpa satuan: 'BUY 3200 | 320K'
        a, b = sorted(v for _, v in cands)
        if PAIR_RATIO[0] <= b / a <= PAIR_RATIO[1]:
            return [("dl", a), ("bgl", b / 100)]
    return []


def parse_message(text: str, author: str) -> list[dict]:
    """-> [{action: 'buy'|'sell'|None, unit, idr_per_dl, author, raw}]"""
    text = EMOJI_RE.sub(_emoji_sub, text)
    msg_actions = {("sell" if a.lower() in SELL_WORDS else "buy") for a in (m[1] for m in ACTION_RE.finditer(text))}
    msg_action = next(iter(msg_actions)) if len(msg_actions) == 1 else None
    out = []
    for line in text.splitlines():
        act = ACTION_RE.search(line)
        action = ("sell" if act[1].lower() in SELL_WORDS else "buy") if act else msg_action
        for unit, price in _read_line(line):
            out.append({"action": action, "unit": unit, "idr_per_dl": price, "author": author, "raw": line.strip()[:160]})
    return out


def iqr_filter(xs: list[float], k: float = 1.5) -> list[float]:
    if len(xs) < 4:
        return xs
    q1, _, q3 = quantiles(xs, n=4, method="inclusive")
    spread = max(q3 - q1, 0.05 * median(xs))
    return [x for x in xs if q1 - k * spread <= x <= q3 + k * spread]


def summarize(offers: list[dict], day: str, lo: float, hi: float) -> tuple[dict | None, str]:
    offers = [o for o in offers if lo <= o["idr_per_dl"] <= hi]
    if not offers:
        return None, "tidak ada bacaan dalam batas wajar"
    center = median(o["idr_per_dl"] for o in offers)
    offers = [o for o in offers if center / BAND <= o["idr_per_dl"] <= center * BAND]
    buy = iqr_filter([o["idr_per_dl"] for o in offers if o["action"] == "buy"])
    sell = iqr_filter([o["idr_per_dl"] for o in offers if o["action"] == "sell"])
    if len(buy) < MIN_SIDE_POSTS or len(sell) < MIN_SIDE_POSTS:
        return None, f"postingan buy={len(buy)}, sell={len(sell)} (butuh >= {MIN_SIDE_POSTS} per sisi)"
    buy_m, sell_m = median(buy), median(sell)
    if buy_m > sell_m * 1.02:
        return None, f"buy ({buy_m:.0f}) > sell ({sell_m:.0f}): tidak masuk akal, kemungkinan salah baca"

    def by_unit(u):   # titik tengah buy/sell hanya dari postingan satuan ini (untuk memeriksa BGL = 100 DL)
        b = [o["idr_per_dl"] for o in offers if o["unit"] == u and o["action"] == "buy"]
        s = [o["idr_per_dl"] for o in offers if o["unit"] == u and o["action"] == "sell"]
        return round((median(b) + median(s)) / 2, 2) if len(b) >= MIN_SIDE_POSTS and len(s) >= MIN_SIDE_POSTS else None

    return {
        "date": day,
        "idr_per_dl": round((buy_m + sell_m) / 2, 2),
        "buy_idr_per_dl": round(buy_m, 2),
        "sell_idr_per_dl": round(sell_m, 2),
        "idr_per_dl_from_dl": by_unit("dl"),
        "idr_per_dl_from_bgl": by_unit("bgl"),
        "posts": len(buy) + len(sell),
        "authors": len({o["author"] for o in offers}),
    }, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--backfill", nargs=2, type=date.fromisoformat, metavar=("MULAI", "AKHIR"))
    ap.add_argument("--channels", default=os.getenv("IDR_CHANNEL_IDS", DEFAULT_CHANNELS), help="ID channel, pisahkan koma")
    ap.add_argument("--sample", type=int, default=0, help="tampilkan N bacaan mentah (tanpa menyimpan)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--min-idr", type=float, default=100, help="batas bawah wajar, rupiah per DL")
    ap.add_argument("--max-idr", type=float, default=1_000_000, help="batas atas wajar, rupiah per DL")
    args = ap.parse_args()

    channels = [int(x) for x in args.channels.split(",") if x.strip()]
    if not args.date and not args.backfill:
        sys.exit("Pilih --date atau --backfill.")

    from dotenv import load_dotenv   # impor berat ditunda supaya parsing bisa diuji tanpa dependensi
    load_dotenv()
    import pipeline as pl

    dc = pl.DiscordClient(os.environ["DISCORD_USER_TOKEN"])
    days = [args.date] if args.date else list(pl.daterange(*args.backfill))
    if args.backfill:
        days = [d for d in days if d < pl.today_local()]   # hari ini belum lengkap

    sb = None
    if not (args.dry_run or args.sample):
        from supabase import create_client
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        if not args.force and days:
            have = {r["date"] for r in sb.table("daily_idr_rates").select("date").gte("date", min(days).isoformat())
                    .lte("date", max(days).isoformat()).execute().data}
            days = [d for d in days if d.isoformat() not in have]
            print(f"{len(have)} hari sudah ada, dilewati. Memproses {len(days)} hari.", flush=True)

    for day in sorted(days, reverse=True):
        offers = []
        for m in pl.iter_messages(dc, channels, day):
            offers.extend(parse_message(m["content"], m["author"]["id"]))
        if args.sample:
            print(f"\n=== {day}: {len(offers)} bacaan, {args.sample} pertama ===")
            for o in offers[: args.sample]:
                print(f"  {o['action'] or '-':4} {o['unit']:3} -> Rp{o['idr_per_dl']:>9,.0f}/DL | {o['raw']!r}")
            continue
        row, why = summarize(offers, day.isoformat(), args.min_idr, args.max_idr)
        if row is None:
            print(f"{day}: {len(offers)} bacaan -> dilewati ({why})", flush=True)
            continue
        print(f"{day}: tengah Rp{row['idr_per_dl']:,.0f}/DL (buy {row['buy_idr_per_dl']:,.0f} | sell {row['sell_idr_per_dl']:,.0f}; "
              f"dari DL {row['idr_per_dl_from_dl']}, dari BGL/100 {row['idr_per_dl_from_bgl']}) | {row['posts']} post, {row['authors']} penulis", flush=True)
        if sb is not None:
            sb.table("daily_idr_rates").upsert(row, on_conflict="date").execute()
    return 0


if __name__ == "__main__":
    sys.exit(main())