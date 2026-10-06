"""Jalankan scrape paralel di komputermu sendiri (tanpa GitHub Actions, tanpa batas menit).

    python run_local.py --start 2025-10-05 --end 2026-10-04 --chunks 4
    python run_local.py --start 2021-01-01 --end 2026-10-04 --chunks 4 --skeleton 45 --items ghc

Sama seperti workflow Actions: (opsional) tahap kerangka berurutan, lalu N potongan paralel,
tiap potongan memproses harinya dari terbaru ke terlama. Aman dihentikan (Ctrl+C) dan dijalankan
ulang: hari yang sudah selesai dilewati lewat scrape_log.
Butuh scraper/.env (token) dan venv aktif seperti biasa.
"""
import argparse
import subprocess
import sys
import threading
from datetime import date, timedelta
from pathlib import Path


def split_range(start: date, end: date, chunks: int) -> list[tuple[date, date]]:
    total = (end - start).days + 1
    n = max(1, min(chunks, total, 20))
    size, extra = divmod(total, n)
    out, cur = [], start
    for i in range(n):
        last = cur + timedelta(days=size + (1 if i < extra else 0) - 1)
        out.append((cur, last))
        cur = last + timedelta(days=1)
    return out


def pump(tag: str, proc: subprocess.Popen) -> None:
    for line in proc.stdout:
        print(f"[{tag}] {line.rstrip()}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, required=True)
    ap.add_argument("--end", type=date.fromisoformat, required=True)
    ap.add_argument("--chunks", type=int, default=4)
    ap.add_argument("--skeleton", type=int, default=0, help="tahap kerangka: 1 hari tiap N hari (0 = lewati)")
    ap.add_argument("--items", default="", help="pilihan item, sama seperti pipeline.py --items")
    ap.add_argument("--pipeline", default=str(Path(__file__).with_name("pipeline.py")))
    args = ap.parse_args()

    extra = ["--items", args.items] if args.items else []
    base = [sys.executable, args.pipeline]

    if args.skeleton > 1:
        print(f"== Tahap kerangka (1 hari tiap {args.skeleton} hari), berurutan ==", flush=True)
        r = subprocess.run(base + ["--backfill", args.start.isoformat(), args.end.isoformat(), "--every", str(args.skeleton)] + extra)
        if r.returncode != 0:
            print("Tahap kerangka gagal; hentikan di sini.")
            return r.returncode

    chunks = split_range(args.start, args.end, args.chunks)
    print(f"== {len(chunks)} potongan paralel ==", flush=True)
    procs, threads = [], []
    try:
        for i, (s, e) in enumerate(chunks, 1):
            print(f"   [{i}] {s} s/d {e}", flush=True)
            p = subprocess.Popen(base + ["--backfill", s.isoformat(), e.isoformat()] + extra,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            t = threading.Thread(target=pump, args=(str(i), p), daemon=True)
            t.start()
            procs.append(p)
            threads.append(t)
        codes = [p.wait() for p in procs]
        for t in threads:
            t.join(timeout=5)
    except KeyboardInterrupt:
        print("\nDihentikan. Hari yang sudah selesai tetap tersimpan; jalankan ulang untuk melanjutkan.")
        for p in procs:
            p.terminate()
        return 130
    for i, c in enumerate(codes, 1):
        print(f"potongan {i}: {'selesai' if c == 0 else f'KELUAR DENGAN KODE {c}'}")
    return 0 if all(c == 0 for c in codes) else 1


if __name__ == "__main__":
    sys.exit(main())