"""Kelompok channel Discord. Setiap item menunjuk satu atau lebih kelompok di items.py
(`"channels": "nama-grup"`), jadi tidak perlu mengisi daftar channel manual tiap kali
berpindah item.

ID channel BUKAN rahasia (token yang rahasia), jadi aman disimpan di repo ini.

Cara menambah kelompok:
  1. Aktifkan Developer Mode di Discord (Settings -> Advanced).
  2. Klik kanan channel -> Copy Channel ID.
  3. Tambahkan di GROUPS di bawah, lalu tunjuk dari items.py.

Kelompok "default" otomatis diambil dari variabel DISCORD_CHANNEL_IDS (GitHub Secret /
scraper/.env) bila tidak didefinisikan di GROUPS. Jadi konfigurasi lama tetap berjalan.

PERHATIAN: mengganti isi sebuah kelompok mengubah data yang dibaca untuk item-item yang
memakainya. Pipeline mencatat "sidik jari" daftar channel di scrape_log, sehingga hari
yang sudah di-scrape dengan daftar channel yang LAMA otomatis dianggap belum selesai dan
dikerjakan ulang.
"""
from __future__ import annotations

import hashlib
import os

GROUPS: dict[str, list[int]] = {
    # "rare": [782718904056807494],          # contoh: #buy-sell-rare-items
    # "tools": [111111111111111111, 222222222222222222],
}


def group_ids(name: str) -> list[int]:
    if name in GROUPS:
        return list(GROUPS[name])
    if name == "default":
        ids = [int(x) for x in os.getenv("DISCORD_CHANNEL_IDS", "").split(",") if x.strip()]
        if ids:
            return ids
        raise SystemExit(
            "Kelompok 'default' kosong: isi DISCORD_CHANNEL_IDS (Secret / scraper/.env) "
            "atau definisikan GROUPS['default'] di channels.py."
        )
    raise SystemExit(f"Kelompok channel '{name}' tidak ada di channels.py. Yang tersedia: {sorted(GROUPS) or ['default']}")


def item_groups(cfg: dict) -> list[str]:
    g = cfg.get("channels", "default")
    return [g] if isinstance(g, str) else list(g)


def item_channels(cfg: dict) -> list[int]:
    """Semua channel milik sebuah item (gabungan kelompoknya, tanpa duplikat, urutan tetap)."""
    seen: dict[int, None] = {}
    for name in item_groups(cfg):
        for cid in group_ids(name):
            seen.setdefault(cid, None)
    return list(seen)


def channel_key(ids: list[int]) -> str:
    """Sidik jari daftar channel (urutan tidak berpengaruh)."""
    return hashlib.sha1(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()[:12]