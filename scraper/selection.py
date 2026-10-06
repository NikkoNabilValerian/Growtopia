"""Logika konfigurasi: channel milik item, pemilihan item, validasi, tampilan.
Hanya memakai stdlib, jadi aman dipanggil dari workflow GitHub tanpa memasang dependensi."""
from __future__ import annotations

import hashlib
import os

from settings import CHANNEL_NAMES, ITEMS, PRESETS

ALL_TOKEN = "(semua item aktif)"   # teks pilihan di dropdown Actions
MIN_PLAUSIBLE_ID = 10**15          # ID channel Discord berupa angka 17-19 digit


# ---------------------------------------------------------------- channel
def env_channel_ids() -> list[int]:
    return [int(x) for x in os.getenv("DISCORD_CHANNEL_IDS", "").split(",") if x.strip()]


def item_channels(cfg: dict) -> list[int]:
    """Channel yang dibaca untuk sebuah item. Tanpa `<item>_channel` di config.py dipakai
    DISCORD_CHANNEL_IDS (cara lama)."""
    ids = cfg.get("channel_ids")
    if ids:
        return list(ids)
    env = env_channel_ids()
    if env:
        return env
    raise SystemExit(
        "Item ini belum punya channel: isi <item>_channel di config.py, "
        "atau isi DISCORD_CHANNEL_IDS (Secret / scraper/.env)."
    )


def channel_key(ids: list[int]) -> str:
    """Sidik jari daftar channel (urutan tidak berpengaruh)."""
    return hashlib.sha1(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- pemilihan item
def enabled_items() -> list[str]:
    return [n for n, c in ITEMS.items() if c.get("enabled", True)]


def options() -> list[str]:
    """Semua pilihan yang sah, dipakai untuk dropdown Actions dan pesan error."""
    return [ALL_TOKEN] + [f"preset:{p}" for p in PRESETS] + list(ITEMS)


def resolve_selection(spec: str | None) -> list[str]:
    """Ubah teks pilihan menjadi daftar item.

    Kosong -> semua item aktif. Pisahkan dengan koma. Token yang dikenal:
      all | (semua item aktif)   semua item aktif
      NAMA_ITEM                  item itu (walau _aktif = False)
      preset:NAMA                item dalam PRESET_NAMA
    """
    if not spec or not spec.strip():
        return enabled_items()
    out: list[str] = []

    def add(names):
        for n in names:
            if n not in out:
                out.append(n)

    for tok in (t.strip() for t in spec.split(",")):
        if not tok:
            continue
        low = tok.lower()
        if low == "all" or tok == ALL_TOKEN:
            add(enabled_items())
        elif low.startswith("preset:"):
            p = tok[7:].strip().lower()
            if p not in PRESETS:
                raise ValueError(f"Preset '{p}' tidak ada. Preset yang tersedia: {list(PRESETS) or '(belum ada)'}")
            unknown = [n for n in PRESETS[p] if n not in ITEMS]
            if unknown:
                raise ValueError(f"PRESET_{p} memuat item yang tidak ada: {unknown}")
            add(PRESETS[p])
        elif low in ITEMS:
            add([low])
        else:
            raise ValueError(f"'{tok}' tidak dikenal. Pilihan yang sah: {', '.join(options())}")
    return out


# ---------------------------------------------------------------- validasi & tampilan
def validate() -> list[str]:
    problems = []
    for name, cfg in ITEMS.items():
        for cid in cfg.get("channel_ids") or []:
            if cid < MIN_PLAUSIBLE_ID:
                problems.append(f"{name}_channel: {cid} bukan ID channel yang valid (Copy Channel ID memberi angka 17-19 digit)")
    for p, names in PRESETS.items():
        for n in names:
            if n not in ITEMS:
                problems.append(f"PRESET_{p}: item '{n}' tidak ada")
    return problems


def _channel_label(cfg: dict) -> str:
    ids = cfg.get("channel_ids")
    if not ids:
        n = len(env_channel_ids())
        return f"(DISCORD_CHANNEL_IDS: {n})" if n else "(DISCORD_CHANNEL_IDS kosong)"
    return ", ".join(CHANNEL_NAMES.get(i, str(i)) for i in ids)


def describe() -> str:
    lines = ["ITEM (aktif = ikut saat tidak ada pilihan)", ""]
    lines.append(f"  {'nama':<12}{'aktif':<7}{'label':<22}{'channel':<30}{'sidik jari':<14}alias")
    for name, cfg in ITEMS.items():
        try:
            key = channel_key(item_channels(cfg))
        except SystemExit:
            key = "-"
        weak = cfg.get("weak_aliases", [])
        alias = ", ".join(a + (" (lemah)" if a in weak else "") for a in cfg["aliases"])
        lines.append(
            f"  {name:<12}{('ya' if cfg.get('enabled', True) else 'tidak'):<7}{cfg.get('label', name):<22}"
            f"{_channel_label(cfg):<30}{key:<14}{alias}"
        )
    lines += ["", "CHANNEL YANG DIDEFINISIKAN"]
    lines += [f"  {n} = {i}" for i, n in CHANNEL_NAMES.items()] or ["  (belum ada; item memakai DISCORD_CHANNEL_IDS)"]
    lines += ["", "PRESET"]
    lines += [f"  preset:{p} = {names}" for p, names in PRESETS.items()] or ["  (belum ada)"]
    lines += ["", "PILIHAN YANG SAH UNTUK --items / dropdown Actions", "  " + ", ".join(options())]
    return "\n".join(lines)