"""Module 1: parser pesan Discord Growtopia + penghitung ringkasan harian.

Hanya item di config.py yang diproses. Pesan dibaca per baris, jadi satu
pesan berisi beberapa baris "Sell ..." dihitung sebagai beberapa penawaran.

Satuan harga (WL / DL / BGL) TIDAK diputuskan saat parsing. Parser hanya mencatat
angka mentah + satuan eksplisit (kalau ada). Satuan untuk angka tanpa satuan
("growscan 2720") ditentukan di resolve_offers() berdasarkan level harga hari itu
(anchor), karena skala harga berubah drastis dari tahun ke tahun.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, median, quantiles

# ---------------------------------------------------------------- konfigurasi

# 1 BGL = 100 DL = 10.000 WL. Semua harga dihitung dalam WL dulu.
WL_PER_UNIT = {"wl": 1, "dl": 100, "bgl": 10_000}

# Item yang dipantau dibaca dari config.py (satu-satunya file yang diubah untuk menambah item).
from settings import ITEMS

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
# Angka tanpa satuan yang didahului kata jumlah ("NEED 2", "qty 3") bisa saja harga ("want 550"),
# jadi tidak langsung dibuang: ia hanya diterima bila hasilnya sangat dekat dengan patokan harga
# (dalam WEAK_TOLERANCE kali lipat). Tanpa patokan, angka seperti itu dibuang.
WEAK_TOLERANCE = 1.5
# Penawaran yang harganya lebih dari N kali lipat / kurang dari 1/N dari patokan dibuang
# (mis. "84bgl" saat harga sebenarnya 84 DL). Berlaku juga untuk satuan eksplisit.
# N bergantung pada UMUR patokan: patokan segar (baris tersimpan 1 hari dari hari yang diproses)
# diperlakukan ketat, patokan lama atau tak diketahui umurnya (seed, --anchor-bgl, median
# satuan eksplisit hari itu) lebih longgar karena harga bisa bergeser selama itu.
ANCHOR_TOL_MIN = 2.0       # N untuk patokan berumur 0 hari
ANCHOR_TOL_MAX = 5.0       # batas atas N
ANCHOR_TOL_PER_DAY = 0.05  # N naik segini per hari umur patokan, sampai ANCHOR_TOL_MAX
# Aturan statis cadangan: angka tanpa satuan >= batas ini dianggap DL, selain itu BGL.
BARE_DL_MIN: dict[str, float] = {n: c["bare_dl_min"] for n, c in ITEMS.items() if "bare_dl_min" in c}
DEFAULT_BARE_DL_MIN = 50

MIN_POSTS_TO_STORE = 3   # hari dengan < 3 postingan valid tidak disimpan (median gabungan)
# Median per SISI (buy / sell) lebih rapuh karena sampelnya lebih kecil, jadi aturannya lebih ketat:
MIN_SIDE_POSTS = 5       # satu sisi butuh minimal 5 postingan agar medianya disimpan
SIDE_BAND = 2.0          # postingan satu sisi di luar [median gabungan / 2, median gabungan x 2] dibuang
MAX_CROSS = 1.15         # bid > ask x 1.15 tidak masuk akal: sisi dengan postingan lebih sedikit dibuang
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

WEAK_ALIASES: set[str] = set()
for _item, _cfg in ITEMS.items():
    for _w in _cfg.get("weak_aliases", []):
        if _w.lower() not in [a.lower() for a in _cfg["aliases"]]:
            raise ValueError(f"weak_aliases '{_w}' bukan salah satu alias item {_item} (config.py)")
        WEAK_ALIASES.add(_w.lower())

ALIAS_TO_ITEM: dict[str, str] = {}
for _item, _aliases in TRACKED_ITEMS.items():
    for _a in _aliases:
        _a = _a.lower()
        if ALIAS_TO_ITEM.get(_a, _item) != _item:
            raise ValueError(f"Alias '{_a}' dipakai oleh dua item: {ALIAS_TO_ITEM[_a]} dan {_item} (config.py)")
        ALIAS_TO_ITEM[_a] = _item
ALIAS_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(a) for a in sorted(ALIAS_TO_ITEM, key=len, reverse=True))
    + r")(?![a-z0-9])",
    re.I,
)
# Angka tanpa satuan yang diikuti kata jumlah barang ("2 pcs") adalah jumlah, bukan harga.
QTY_BEFORE_RE = re.compile(r"(?:need|needs|want|wants|qty|quantity|stock|butuh)\W*$", re.I)
QTY_AFTER_RE = re.compile(
    r"\s*(?:pcs?|pieces?|biji|buah|units?|worlds?(?!\s*locks?)|items?|days?|hari|hours?|jam)(?![a-z])", re.I
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
    weak: bool = False     # angka tanpa satuan yang didahului kata jumlah ("need 2"): harus cocok dengan patokan
    raw: str = field(default="", compare=False)   # baris pesan asli, hanya untuk diagnosis


@dataclass(frozen=True)
class Resolved:
    offer: Offer
    price_wl: float | None  # None = dibuang
    how: str                # eksplisit | bare->wl | bare->dl | bare->bgl | bare-statis | dibuang


def mentions_tracked(text: str) -> bool:
    return bool(ALIAS_RE.search(text))


def _canon(word: str) -> str:
    """Bentuk ASCII huruf kecil dari sebuah kata ('BUYİNG' -> 'buying'), untuk pencarian kamus."""
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().lower()


def _normalize(text: str) -> str:
    # NFKC: huruf bergaya (𝗦𝗘𝗟𝗟, ＳＥＬＬ, ᴮᴳᴸ) menjadi huruf biasa. İ/ı (alfabet Turki) tidak ikut
    # berubah, jadi dipetakan manual; tanpa itu 'BUYİNG' lolos regex tetapi gagal di kamus.
    text = unicodedata.normalize("NFKC", text).replace("\u0130", "I").replace("\u0131", "i")
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

        # Semua angka setelah alias. Angka dengan satuan eksplisit diutamakan ("buy gs 2 pcs 78dl"
        # -> 78dl, bukan 2), dan angka tanpa satuan yang diikuti "pcs" dibuang karena itu jumlah.
        cands = [
            m for m in PRICE_RE.finditer(line, last.end())
            if m["unit"] or not QTY_AFTER_RE.match(line, m.end())
        ]
        # Bila item ini hanya disebut lewat alias lemah ("gs"), angka tanpa satuan tidak dipercaya.
        last_item = ALIAS_TO_ITEM.get(_canon(last[0]))
        action = ACTIONS.get(_canon(act[1]))
        if last_item is None or action is None:
            continue  # karakter aneh yang lolos regex tetapi bukan alias/aksi sungguhan
        mentions = [_canon(m[0]) for m in aliases if ALIAS_TO_ITEM.get(_canon(m[0])) == last_item]
        if all(a in WEAK_ALIASES for a in mentions):
            cands = [m for m in cands if m["unit"]]
        if not cands:
            continue
        price = next((m for m in cands if m["unit"]), cands[0])

        value = float(price["num"].replace(",", "."))
        if value <= 0:
            continue
        weak = not price["unit"] and bool(QTY_BEFORE_RE.search(line[: price.start()]))
        offers.append(
            Offer(
                item=last_item,
                action=action,
                value=value,
                unit=(price["unit"] or "").lower() or None,
                author=author,
                weak=weak,
                raw=line.strip()[:200],
            )
        )
    return offers


# ------------------------------------------------------- penentuan satuan

def anchor_value(a) -> float | None:
    """Nilai patokan (WL) dari float atau pasangan (nilai, umur_hari)."""
    return a[0] if isinstance(a, tuple) else a


def anchor_tolerance(age_days: int | None) -> float:
    if age_days is None:
        return ANCHOR_TOL_MAX
    return min(ANCHOR_TOL_MAX, ANCHOR_TOL_MIN + ANCHOR_TOL_PER_DAY * max(age_days, 0))


def _log_dist(a: float, b: float) -> float:
    return abs(math.log10(a / b))


def resolve_offers(offers: list[Offer], anchors: dict | None = None) -> list[Resolved]:
    """Ubah angka mentah menjadi harga dalam WL.

    anchors: {item: patokan} dengan patokan berupa level harga dalam WL (umur tak diketahui)
    atau pasangan (WL, umur_hari) dari harga tersimpan terdekat. Boleh kosong.
    """
    anchors = anchors or {}
    by_item: dict[str, list[Offer]] = defaultdict(list)
    for o in offers:
        by_item[o.item].append(o)

    out: list[Resolved] = []
    for item, offs in by_item.items():
        raw = anchors.get(item)
        anchor = anchor_value(raw)
        age = raw[1] if isinstance(raw, tuple) else None   # None = umur tak diketahui -> toleransi longgar
        if not anchor:
            explicit = [o.value * WL_PER_UNIT[o.unit] for o in offs if o.unit]
            if len(explicit) >= MIN_EXPLICIT_FOR_ANCHOR:
                anchor = median(explicit)
        tol_anchor = anchor_tolerance(age)

        for o in offs:
            if o.unit:
                wl, how = o.value * WL_PER_UNIT[o.unit], "eksplisit"
            elif anchor:
                unit = min(WL_PER_UNIT, key=lambda u: _log_dist(o.value * WL_PER_UNIT[u], anchor))
                wl, how = o.value * WL_PER_UNIT[unit], f"bare->{unit}"
            else:
                if o.weak:  # tanpa patokan, angka ambigu seperti "need 2" tidak bisa dipercaya
                    out.append(Resolved(o, None, "dibuang"))
                    continue
                unit = "dl" if o.value >= BARE_DL_MIN.get(item, DEFAULT_BARE_DL_MIN) else "bgl"
                wl, how = o.value * WL_PER_UNIT[unit], "bare-statis"

            tol = WEAK_TOLERANCE if (o.weak and not o.unit) else tol_anchor
            if anchor and _log_dist(wl, anchor) > math.log10(tol):
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


def _segment(prices: list[float], center: float) -> tuple[float | None, int]:
    """(median satu sisi, jumlah postingan sisi itu).

    Postingan yang jauh dari median gabungan hari itu (`center`) dibuang lebih dulu, karena
    filter IQR tidak berjalan untuk sampel kecil (< 4) dan satu sisi sering hanya punya
    beberapa postingan. Median None bila sisa postingan < MIN_SIDE_POSTS.
    """
    kept = [p for p in prices if center / SIDE_BAND <= p <= center * SIDE_BAND]
    if len(kept) < MIN_SIDE_POSTS:
        return None, len(prices)
    clean = iqr_filter(kept)
    return (round(median(clean), 4) if clean else None), len(prices)


def summarize_day(
    offers: list[Offer], day: str, anchors: dict | None = None
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
        center = median(clean)  # median gabungan hari itu, setelah filter IQR
        buy_median, buy_volume = _segment(g["buy"], center)
        sell_median, sell_volume = _segment(g["sell"], center)
        if buy_median and sell_median and buy_median > sell_median * MAX_CROSS:
            # Bid jauh di atas ask: salah satu sisi pasti keliru. Buang yang lebih sedikit datanya.
            if buy_volume <= sell_volume:
                buy_median = None
            else:
                sell_median = None
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