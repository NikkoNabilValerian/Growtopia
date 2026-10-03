"""Module 1: parser pesan Discord Growtopia + penghitung ringkasan harian."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, quantiles

# Konversi lock ke WL. Semua harga dinormalisasi ke WL dulu (integer-friendly),
# lalu diubah ke BGL saat diringkas.
WL_PER_UNIT = {"wl": 1, "dl": 100, "bgl": 10_000}

ACTIONS = {
    "sell": "sell", "selling": "sell", "wts": "sell",
    "buy": "buy", "buying": "buy", "wtb": "buy",
}

# Alias nama item -> nama kanonik. Isi sesuai kebutuhan, contoh:
# ALIASES = {"ghc": "ghc", "magplant": "magplant 5000"}
ALIASES: dict[str, str] = {}

OFFER_RE = re.compile(
    r"""
    (?<![a-z0-9])
    (?P<action>sell|selling|wts|buy|buying|wtb)\s+
    (?P<item>[a-z][a-z0-9'\- ]{1,40}?)\s+
    (?P<price>\d+(?:[.,]\d+)?)\s*(?P<unit>bgl|dl|wl)s?\b
    (?:\s+(?:at|in|@)\s+(?P<world>[a-z0-9]{1,24}))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

MIN_POSTS_TO_STORE = 3   # hari dengan sampel < 3 postingan tidak disimpan
IQR_K = 1.5
# False = semua postingan dihitung, termasuk harga yang sama berulang
# (median yang menentukan harga akhir). True = satu penulis + harga sama = 1 suara.
DEDUPE = False


@dataclass(frozen=True)
class Offer:
    item: str
    action: str       # "buy" | "sell"
    price_wl: float
    author: str


def normalize_item(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw.strip().lower())
    return ALIASES.get(name, name)


def parse_message(text: str, author: str) -> list[Offer]:
    """Satu pesan bisa memuat beberapa penawaran, jadi pakai finditer."""
    offers: list[Offer] = []
    for m in OFFER_RE.finditer(text):
        price = float(m["price"].replace(",", "."))
        price_wl = price * WL_PER_UNIT[m["unit"].lower()]
        if price_wl <= 0:
            continue
        offers.append(
            Offer(
                item=normalize_item(m["item"]),
                action=ACTIONS[m["action"].lower()],
                price_wl=price_wl,
                author=author,
            )
        )
    return offers


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
    samples = [
        ("sell ghc 30bgl at MUKEL", "a"),
        ("buy bgl 20wl at WORLD", "b"),
        ("SELL GHC 31 bgl at ABC | buy rayman 4.5bgl in XYZ", "c"),
        ("sell ghc 32bgl", "d"),
        ("sell ghc 30bgl at MUKEL", "a"),      # harga sama diulang: tetap dihitung
        ("sell lock 150dl at X | buy lock 45wl at Y", "f"),
        ("sell ghc 9999bgl at TROLL", "e"),    # troll
    ]
    offers = [o for text, a in samples for o in parse_message(text, a)]
    for o in offers:
        print(o)
    print(summarize_day(offers, "2026-10-02"))