"""Module 1: parser pesan Discord Growtopia + penghitung ringkasan harian.

Hanya item di TRACKED_ITEMS yang diproses. Pesan dibaca per baris, jadi satu
pesan berisi beberapa baris "Sell ..." dihitung sebagai beberapa penawaran.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, quantiles

# ---------------------------------------------------------------- konfigurasi

# 1 BGL = 100 DL = 10.000 WL. Semua harga dihitung dalam WL dulu.
WL_PER_UNIT = {"wl": 1, "dl": 100, "bgl": 10_000}

# Item yang dipantau: nama di database -> alias yang dipakai orang di chat.
# Tambah item baru di sini, mis. "magplant": ["magplant", "mag"].
TRACKED_ITEMS: dict[str, list[str]] = {
    "growscan": ["growscan", "gscan", "gs"],
}

# Angka TANPA satuan (mis. "growscan 550"): >= batas ini dianggap DL,
# di bawahnya dianggap BGL. Sesuaikan per item bila harganya jauh berbeda.
BARE_DL_MIN: dict[str, float] = {"growscan": 50}
DEFAULT_BARE_DL_MIN = 50

# Emoji custom Discord muncul di teks mentah sebagai <:nama:id>.
# Dicocokkan lewat nama (huruf kecil, tanpa underscore) atau lewat id.
# Kalau emoji tidak dikenali, angkanya diperlakukan sebagai "tanpa satuan".
EMOJI_NAME_UNITS = {
    "bgl": "bgl", "bluegemlock": "bgl",
    "dl": "dl", "diamondlock": "dl",
    "wl": "wl", "worldlock": "wl",
}
EMOJI_ID_UNITS: dict[str, str] = {
    "880251420413161533": "bgl",
    "880251434380165130": "dl",
    "880251447470596157": "wl",
}

# Bagian nama item yang berupa angka (bukan harga), mis. "Growscan 9000".
NOISE_PATTERNS = [
    re.compile(r"(?<![a-z0-9])(growscan|gscan)\s*9000(?![a-z0-9])", re.I),
]

MIN_POSTS_TO_STORE = 3   # hari dengan sampel < 3 postingan tidak disimpan
IQR_K = 1.5
# False = semua postingan dihitung, termasuk harga yang sama berulang
# (median yang menentukan harga akhir). True = satu penulis + harga sama = 1 suara.
DEDUPE = False

# ------------------------------------------------------------------ regex

ACTIONS = {
    "sell": "sell", "selling": "sell", "wts": "sell",
    "buy": "buy", "buying": "buy", "wtb": "buy",
}
ACTION_RE = re.compile(r"(?<![a-z0-9])(sell|selling|wts|buy|buying|wtb)(?![a-z0-9])", re.I)
EMOJI_RE = re.compile(r"<a?:(\w+):(\d+)>")

ALIAS_TO_ITEM = {a.lower(): item for item, aliases in TRACKED_ITEMS.items() for a in aliases}
ALIAS_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(a) for a in sorted(ALIAS_TO_ITEM, key=len, reverse=True))
    + r")(?![a-z0-9])",
    re.I,
)
PRICE_RE = re.compile(
    r"(?<![\w.,])(?P<num>\d+(?:[.,]\d{1,2})?)\s*(?:(?P<unit>bgl|dl|wl)s?)?(?![a-z0-9])",
    re.I,
)


@dataclass(frozen=True)
class Offer:
    item: str
    action: str       # "buy" | "sell"
    price_wl: float
    author: str


def mentions_tracked(text: str) -> bool:
    return bool(ALIAS_RE.search(text))


def _normalize(text: str) -> str:
    def emoji(m: re.Match) -> str:
        unit = EMOJI_ID_UNITS.get(m[2]) or EMOJI_NAME_UNITS.get(m[1].lower().replace("_", ""))
        return f" {unit} " if unit else " "

    text = EMOJI_RE.sub(emoji, text)  # juga membuang id emoji agar tidak terbaca sebagai harga
    for pat in NOISE_PATTERNS:
        text = pat.sub(r"\1", text)
    return text


def parse_message(text: str, author: str) -> list[Offer]:
    text = _normalize(text)
    msg_action = ACTION_RE.search(text)
    offers: list[Offer] = []

    for line in text.splitlines():
        aliases = list(ALIAS_RE.finditer(line))
        if not aliases:
            continue
        last = aliases[-1]  # "GROWSCAN GS GSCAN 6" -> harga dicari setelah alias terakhir

        act = ACTION_RE.search(line) or msg_action
        if not act:
            continue  # tanpa buy/sell kemungkinan bukan promosi (mis. pertanyaan harga)

        price = PRICE_RE.search(line, last.end())
        if not price:
            continue

        item = ALIAS_TO_ITEM[last[0].lower()]
        num = float(price["num"].replace(",", "."))
        unit = (price["unit"] or "").lower()
        if not unit:
            unit = "dl" if num >= BARE_DL_MIN.get(item, DEFAULT_BARE_DL_MIN) else "bgl"

        price_wl = num * WL_PER_UNIT[unit]
        if price_wl <= 0:
            continue
        offers.append(Offer(item, ACTIONS[act[1].lower()], price_wl, author))
    return offers


# -------------------------------------------------------------- ringkasan

def iqr_filter(prices: list[float], k: float = IQR_K) -> list[float]:
    """Buang outlier (harga troll/spam) dengan metode IQR."""
    if len(prices) < 4:
        return prices
    q1, _, q3 = quantiles(prices, n=4, method="inclusive")
    # Batas minimal 5% dari median agar data yang sangat seragam
    # (IQR = 0) tidak membuang harga yang wajar.
    spread = max(q3 - q1, 0.05 * median(prices))
    lo, hi = q1 - k * spread, q3 + k * spread
    return [p for p in prices if lo <= p <= hi]


def summarize_day(offers: list[Offer], day: str, actions: set[str] | None = None) -> list[dict]:
    """Ubah semua penawaran satu hari menjadi 1 baris ringkasan per item.

    actions: batasi ke {"sell"} atau {"buy"}; None = gabungan keduanya
    (sesuai skema tabel yang hanya punya satu baris per item per hari).
    """
    selected = [o for o in offers if actions is None or o.action in actions]
    if DEDUPE:
        selected = list({(o.author, o.item, o.action, o.price_wl): o for o in selected}.values())

    by_item: dict[str, list[float]] = defaultdict(list)
    for o in selected:
        by_item[o.item].append(o.price_wl / 10_000)  # WL -> BGL

    rows = []
    for item, prices in by_item.items():
        if len(prices) < MIN_POSTS_TO_STORE:
            continue
        clean = iqr_filter(prices)
        if not clean:
            continue
        rows.append(
            {
                "item_name": item,
                "date": day,
                "avg_price": round(mean(clean), 4),
                "median_price": round(median(clean), 4),
                "min_price": round(min(clean), 4),
                "max_price": round(max(clean), 4),
                "total_volume": len(prices),  # sebelum filter IQR
            }
        )
    return rows


if __name__ == "__main__":
    # Contoh dari screenshot channel buy-sell-rare-items
    samples = [
        ("Sell GROWSCAN GS GSCAN 6 <:bgl:111> NO LESS\nSell GROWSCAN GS GSCAN 6 <:bgl:111> NO LESS", "wasup"),
        ("BUY GROWSCAN GS GSCAN 6 💎", "ky"),
        ("Buy Growscan 500 <:dl:222>", "user310"),
        ("Buy Magplant 16 <:bgl:111>\nBuy Growscan / gs 550 <:dl:222>\nBuy Swordfish Sword / sfs 2.5 <:bgl:111>", "nox"),
        ("buy growscan / gs / gscan 550\ndm me", "nihun"),
        ("Sell growscan 590 <:dl:222> dm me\n\nSell growscan 590 <:dl:222> dm me", "kolibri"),
        ("sell growscan 9000 6bgl", "x"),            # "9000" = nama item, bukan harga
        ("how much is growscan 6?", "y"),            # tanpa buy/sell: diabaikan
        ("sell growscan 9999bgl", "troll"),
    ]
    offers = [o for text, a in samples for o in parse_message(text, a)]
    for o in offers:
        print(o)
    print(summarize_day(offers, "2026-10-02"))