"""Module 1: parser pesan Discord Growtopia + penghitung ringkasan harian.

Hanya item di items.py yang diproses. Pesan dibaca per baris, jadi satu
pesan berisi beberapa baris "Sell ..." dihitung sebagai beberapa penawaran.

Satuan harga (WL / DL / BGL) TIDAK diputuskan saat parsing. Parser hanya mencatat
angka mentah + satuan eksplisit (kalau ada). Satuan untuk angka tanpa satuan
("growscan 2720") ditentukan di resolve_offers() berdasarkan level harga hari itu
(anchor), karena skala harga berubah drastis dari tahun ke tahun.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, quantiles

# ---------------------------------------------------------------- konfigurasi

# 1 BGL = 100 DL = 10.000 WL. Semua harga dihitung dalam WL dulu.
WL_PER_UNIT = {"wl": 1, "dl": 100, "bgl": 10_000}

# Item yang dipantau dibaca dari items.py (satu-satunya file yang diubah untuk menambah item).
from items import ITEMS

TRACKED_ITEMS: dict[str, list[str]] = {name: cfg["aliases"] for name, cfg in ITEMS.items()}
ITEM_LABELS: dict[str, str] = {name: cfg.get("label", name) for name, cfg in ITEMS.items()}

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

# Bagian nama item yang berupa angka (bukan harga), mis. "Growscan 9000" -> "growscan".
NOISE_PATTERNS = [
    re.compile(r"(?<![a-z0-9])(?:" + pat + r")(?![a-z0-9])", re.I)
    for cfg in ITEMS.values()
    for pat in cfg.get("noise", [])
]

# --- Penentuan satuan untuk angka tanpa satuan -------------------------------
# Anchor = perkiraan level harga (dalam WL) pada hari itu. Sumbernya (berurutan):
#   1. harga tersimpan terdekat di database (diberikan oleh pipeline),
#   2. median penawaran dengan satuan eksplisit pada hari itu (min. 3 buah),
#   3. aturan statis di bawah (hanya jika tidak ada anchor sama sekali).
# Angka tanpa satuan dijadikan WL / DL / BGL, mana yang paling dekat dengan anchor.
MIN_EXPLICIT_FOR_ANCHOR = 3
# Penawaran yang harganya lebih dari N kali lipat / kurang dari 1/N dari anchor
# dibuang (mis. "84bgl" saat harga sebenarnya 84 DL). Berlaku juga untuk satuan eksplisit.
ANCHOR_TOLERANCE = 5.0
# Aturan statis cadangan: angka tanpa satuan >= batas ini dianggap DL, selain itu BGL.
BARE_DL_MIN: dict[str, float] = {n: c["bare_dl_min"] for n, c in ITEMS.items() if "bare_dl_min" in c}
DEFAULT_BARE_DL_MIN = 50

MIN_POSTS_TO_STORE = 3   # hari/sisi dengan sampel < 3 postingan tidak disimpan
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

ALIAS_TO_ITEM: dict[str, str] = {}
for _item, _aliases in TRACKED_ITEMS.items():
    for _a in _aliases:
        _a = _a.lower()
        if ALIAS_TO_ITEM.get(_a, _item) != _item:
            raise ValueError(f"Alias '{_a}' dipakai oleh dua item: {ALIAS_TO_ITEM[_a]} dan {_item} (items.py)")
        ALIAS_TO_ITEM[_a] = _item
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
    action: str            # "buy" | "sell"
    value: float           # angka mentah seperti yang diketik
    unit: str | None       # "wl" | "dl" | "bgl" | None (tanpa satuan)
    author: str


@dataclass(frozen=True)
class Resolved:
    offer: Offer
    price_wl: float | None  # None = dibuang
    how: str                # eksplisit | bare->wl | bare->dl | bare->bgl | bare-statis | dibuang


def mentions_tracked(text: str) -> bool:
    return bool(ALIAS_RE.search(text))


def _normalize(text: str) -> str:
    def emoji(m: re.Match) -> str:
        unit = EMOJI_ID_UNITS.get(m[2]) or EMOJI_NAME_UNITS.get(m[1].lower().replace("_", ""))
        return f" {unit} " if unit else " "

    text = EMOJI_RE.sub(emoji, text)  # juga membuang id emoji agar tidak terbaca sebagai harga
    for pat in NOISE_PATTERNS:
        text = pat.sub(lambda m: m.group(1) or "", text)
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

        value = float(price["num"].replace(",", "."))
        if value <= 0:
            continue
        offers.append(
            Offer(
                item=ALIAS_TO_ITEM[last[0].lower()],
                action=ACTIONS[act[1].lower()],
                value=value,
                unit=(price["unit"] or "").lower() or None,
                author=author,
            )
        )
    return offers


# ------------------------------------------------------- penentuan satuan

def _log_dist(a: float, b: float) -> float:
    return abs(math.log10(a / b))


def resolve_offers(offers: list[Offer], anchors: dict[str, float | None] | None = None) -> list[Resolved]:
    """Ubah angka mentah menjadi harga dalam WL.

    anchors: {item: level harga dalam WL} dari harga tersimpan terdekat (boleh kosong).
    """
    anchors = anchors or {}
    by_item: dict[str, list[Offer]] = defaultdict(list)
    for o in offers:
        by_item[o.item].append(o)

    out: list[Resolved] = []
    for item, offs in by_item.items():
        anchor = anchors.get(item)
        if not anchor:
            explicit = [o.value * WL_PER_UNIT[o.unit] for o in offs if o.unit]
            if len(explicit) >= MIN_EXPLICIT_FOR_ANCHOR:
                anchor = median(explicit)

        for o in offs:
            if o.unit:
                wl, how = o.value * WL_PER_UNIT[o.unit], "eksplisit"
            elif anchor:
                unit = min(WL_PER_UNIT, key=lambda u: _log_dist(o.value * WL_PER_UNIT[u], anchor))
                wl, how = o.value * WL_PER_UNIT[unit], f"bare->{unit}"
            else:
                unit = "dl" if o.value >= BARE_DL_MIN.get(item, DEFAULT_BARE_DL_MIN) else "bgl"
                wl, how = o.value * WL_PER_UNIT[unit], "bare-statis"

            if anchor and _log_dist(wl, anchor) > math.log10(ANCHOR_TOLERANCE):
                out.append(Resolved(o, None, "dibuang"))
                continue
            out.append(Resolved(o, wl, how))
    return out


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


def _segment(prices: list[float]) -> tuple[float | None, int]:
    """(median setelah filter IQR, jumlah postingan). Median None bila sampel kurang."""
    if len(prices) < MIN_POSTS_TO_STORE:
        return None, len(prices)
    clean = iqr_filter(prices)
    return (round(median(clean), 4) if clean else None), len(prices)


def summarize_day(
    offers: list[Offer], day: str, anchors: dict[str, float | None] | None = None
) -> list[dict]:
    """Ubah semua penawaran satu hari menjadi 1 baris ringkasan per item.

    Kolom gabungan (avg/median/min/max/total_volume) memakai buy + sell.
    buy_median / sell_median dihitung terpisah; None bila postingan < MIN_POSTS_TO_STORE.
    Harga disimpan dalam BGL.
    """
    resolved = [r for r in resolve_offers(offers, anchors) if r.price_wl is not None]
    if DEDUPE:
        seen, kept = set(), []
        for r in resolved:
            key = (r.offer.author, r.offer.item, r.offer.action, r.price_wl)
            if key not in seen:
                seen.add(key)
                kept.append(r)
        resolved = kept

    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"all": [], "buy": [], "sell": []})
    by_author: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    side_authors: dict[str, dict[str, set]] = defaultdict(lambda: {"buy": set(), "sell": set()})
    for r in resolved:
        bgl = r.price_wl / 10_000  # WL -> BGL
        o = r.offer
        groups[o.item]["all"].append(bgl)
        groups[o.item][o.action].append(bgl)
        by_author[o.item][o.author].append(bgl)
        side_authors[o.item][o.action].add(o.author)

    rows = []
    for item, g in groups.items():
        if len(g["all"]) < MIN_POSTS_TO_STORE:
            continue
        clean = iqr_filter(g["all"])
        if not clean:
            continue
        buy_median, buy_volume = _segment(g["buy"])
        sell_median, sell_volume = _segment(g["sell"])
        # Satu suara per penulis: median dari median tiap penulis. Tidak terpengaruh
        # penulis yang mengulang postingan puluhan kali.
        author_prices = [median(v) for v in by_author[item].values()]
        author_median = round(median(iqr_filter(author_prices) or author_prices), 4)
        rows.append(
            {
                "item_name": item,
                "date": day,
                "avg_price": round(mean(clean), 4),
                "median_price": round(median(clean), 4),   # gabungan
                "author_median": author_median,
                "min_price": round(min(clean), 4),
                "max_price": round(max(clean), 4),
                "total_volume": len(g["all"]),              # sebelum filter IQR
                "buy_median": buy_median,
                "sell_median": sell_median,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "total_authors": len(by_author[item]),
                "buy_authors": len(side_authors[item]["buy"]),
                "sell_authors": len(side_authors[item]["sell"]),
            }
        )
    return rows


if __name__ == "__main__":
    def show(title, texts, anchor_bgl=None):
        offers = [o for i, t in enumerate(texts) for o in parse_message(t, str(i))]
        anchors = {"growscan": anchor_bgl * 10_000} if anchor_bgl else None
        print(f"\n== {title} (anchor: {anchor_bgl} BGL)" if anchor_bgl else f"\n== {title} (tanpa anchor)")
        for r in resolve_offers(offers, anchors):
            o = r.offer
            price = f"{r.price_wl / 10_000:.4f} BGL" if r.price_wl is not None else "-"
            print(f"  {o.action:4} {o.value:g} {o.unit or '(bare)':6} -> {price:>12}  [{r.how}]")
        print("  ringkasan:", [(x["median_price"], x["buy_median"], x["sell_median"]) for x in summarize_day(offers, "2023-04-20", anchors)])

    # Era WL: orang menulis "2720" artinya 2720 WL (= 27,2 DL = 0,272 BGL)
    old_era = ["sell growscan 2720", "buy gs 2600", "sell growscan 2800", "sell growscan 27dl",
               "buy growscan 2650", "sell growscan 8400 bgl", "sell growscan 8400"]
    show("era lama, anchor dari tetangga 0.27 BGL", old_era, anchor_bgl=0.27)
    show("era lama, TANPA anchor (hanya 1 eksplisit -> aturan statis)", old_era)

    # Era sekarang
    now_era = ["Sell growscan 610 <:DL:880251434380165130>", "buy growscan 550", "sell GS GSCAN 6 <:BGL:880251420413161533>",
               "sell growscan 6", "buy gs 5500", "sell growscan 9999bgl"]
    show("era sekarang, anchor 6.0 BGL", now_era, anchor_bgl=6.0)