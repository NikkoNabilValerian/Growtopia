#!/usr/bin/env python3
"""Uji apakah harga benar-benar turun di sekitar event (event study + uji plasebo kalender digeser).

Pertanyaan yang dijawab: "pada tanggal-tanggal event, harga bergerak lebih rendah dari
tren-nya DIBANDING bila kalender event yang SAMA digeser ke tanggal lain?" Itu lebih kuat daripada melihat
chart dan merasa harganya turun, karena harga item ini punya tren naik besar dan lonjakan
acak yang bisa tampak seperti pola.

Contoh:
  python analysis/event_study.py --items ghc,growscan --event valentine
  python analysis/event_study.py --items ghc --event summerfest --stat 3 21
  python analysis/event_study.py --items ghc,growscan --explore      # peta musiman tanpa kalender event
  python analysis/event_study.py --items ghc,growscan --event valentine --power   # seberapa kecil efek yang bisa terdeteksi?
  python analysis/event_study.py --csv harga.csv --events-csv events.csv --event valentine

Data dibaca dari Supabase (SUPABASE_URL dan SUPABASE_KEY / SUPABASE_SERVICE_KEY di lingkungan atau
scraper/.env), kecuali memakai --csv. Kalender event dari tabel `events` (kolom name, start_date,
end_date). Satu event berulang cukup diberi nama yang memuat kata kunci yang sama, mis.
"Valentine 2023", "Valentine 2024". t=0 adalah start_date.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- data
def _client():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / "scraper" / ".env")
    except ImportError:
        pass
    from supabase import create_client
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not key or not os.environ.get("SUPABASE_URL"):
        sys.exit("Isi SUPABASE_URL dan SUPABASE_KEY (atau SUPABASE_SERVICE_KEY), atau pakai --csv.")
    return create_client(os.environ["SUPABASE_URL"], key)


def _fetch_all(table: str, **filters) -> pd.DataFrame:
    sb, rows = _client(), []
    for offset in range(0, 1_000_000, 1000):
        q = sb.table(table).select("*")
        for k, v in filters.items():
            q = q.eq(k, v)
        data = q.range(offset, offset + 999).execute().data
        rows += data
        if len(data) < 1000:
            break
    return pd.DataFrame(rows)


def load_prices(args) -> pd.DataFrame:
    df = pd.read_csv(args.csv, parse_dates=["date"]) if args.csv else _fetch_all("daily_item_prices")
    if df.empty:
        sys.exit("Tidak ada data harga.")
    df["date"] = pd.to_datetime(df["date"])
    if "total_volume" not in df:
        df["total_volume"] = 10**9
    return df[df["item_name"].isin(args.items)]


def load_events(args) -> pd.DataFrame:
    df = pd.read_csv(args.events_csv) if args.events_csv else _fetch_all("events")
    if df.empty:
        sys.exit("Tabel events kosong. Isi tanggal event dulu (lihat petunjuk), atau pakai --explore.")
    for c in ("start_date", "end_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def build_series(g: pd.DataFrame, min_volume: int, max_gap: int = 3) -> pd.Series:
    """log(median gabungan) harian. Hari berpostingan tipis dianggap kosong; celah <= max_gap hari diinterpolasi."""
    g = g.sort_values("date").drop_duplicates("date")
    g = g[g["total_volume"] >= min_volume]
    s = pd.Series(np.log(g["median_price"].astype(float).values), index=pd.DatetimeIndex(g["date"]))
    idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
    return s.reindex(idx).interpolate(limit=max_gap, limit_area="inside")


# --------------------------------------------------------------------------- inti
def ar_profile(x: np.ndarray, i: int, a) -> np.ndarray | None:
    """Selisih log-harga dari tren/baseline sebelum event, untuk offset t = -pre..+post. None bila data kurang."""
    t = np.arange(-a.pre, a.post + 1)
    first = i + min(-a.pre, a.trend[0], a.base[0])
    if first < 0 or i + a.post >= len(x):
        return None
    if a.detrend == "slope":
        w = np.arange(a.trend[0], a.trend[1] + 1)
        y = x[i + w]
        m = np.isfinite(y)
        if m.sum() < 0.6 * len(w):
            return None
        b, c = np.polyfit(w[m], y[m], 1)
        base = c + b * t
    else:
        w = np.arange(a.base[0], a.base[1] + 1)
        y = x[i + w]
        m = np.isfinite(y)
        if m.sum() < 0.6 * len(w):
            return None
        base = np.full(len(t), y[m].mean())
    return x[i + t] - base


def stat_of(ar: np.ndarray | None, a) -> float:
    if ar is None:
        return np.nan
    t = np.arange(-a.pre, a.post + 1)
    seg = ar[(t >= a.stat[0]) & (t <= a.stat[1])]
    return float(np.nanmean(seg)) if np.isfinite(seg).sum() >= 0.6 * len(seg) else np.nan


def pre_slope_pct(x: np.ndarray, i: int, a) -> float:
    w = np.arange(a.trend[0], a.trend[1] + 1)
    if i + w[0] < 0:
        return np.nan
    y = x[i + w]
    m = np.isfinite(y)
    return float(np.polyfit(w[m], y[m], 1)[0] * 100) if m.sum() >= 0.6 * len(w) else np.nan


def pct(v):
    return (np.exp(v) - 1) * 100


def run(args) -> int:
    prices = load_prices(args)
    series = {it: build_series(prices[prices["item_name"] == it], args.min_volume) for it in args.items if (prices["item_name"] == it).any()}
    if not series:
        sys.exit("Item tidak ditemukan di data.")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.explore:
        return explore(series, out)

    events = load_events(args)
    chosen = events[events["name"].str.contains(args.event, case=False, na=False)].sort_values("start_date")
    if chosen.empty:
        sys.exit(f"Tidak ada event yang namanya memuat '{args.event}'. Event yang ada: {sorted(events['name'].unique())}")
    rng = np.random.default_rng(args.seed)
    if args.power:
        return power(series, chosen, args)

    # AR dan statistik untuk SEMUA tanggal tiap item (dipakai kejadian asli maupun kalender yang digeser)
    S_arr, AR_arr, dates_of = {}, {}, {}
    for it, lp in series.items():
        x, dates = lp.to_numpy(), lp.index
        dates_of[it] = dates
        ars = [ar_profile(x, i, args) for i in range(len(dates))]
        S_arr[it] = np.array([stat_of(ar, args) for ar in ars])
        AR_arr[it] = np.array([ar if ar is not None else np.full(args.pre + args.post + 1, np.nan) for ar in ars])

    units = []
    for it, lp in series.items():
        x, dates = lp.to_numpy(), dates_of[it]
        for _, ev in chosen.iterrows():
            i = (ev["start_date"] - dates[0]).days
            if 0 <= i < len(dates) and np.isfinite(S_arr[it][i]):
                units.append({"item": it, "event": ev["name"], "start": ev["start_date"].date(), "i": i,
                              "S": float(S_arr[it][i]), "ar": AR_arr[it][i], "slope": pre_slope_pct(x, i, args)})
    if not units:
        sys.exit("Tidak ada kejadian event yang punya data cukup (cek rentang tanggal data dan --min-volume).")
    n = len(units)
    S = np.array([u["S"] for u in units])
    t = np.arange(-args.pre, args.post + 1)

    # --- uji plasebo: geser SELURUH kalender event dengan selisih k hari yang sama untuk semua item.
    # Menjaga korelasi antar-item dan antar-waktu. Di bawah hipotesis "tidak ada efek event", T pada kalender
    # asli sebanding dengan T pada kalender yang digeser, jadi p-value = peringkatnya di antara semuanya.
    shifts, Tk, prof = [], [], []
    for k in range(-args.max_shift, args.max_shift + 1):
        if k == 0 or abs(k) < args.min_shift:
            continue
        vals, arrs = [], []
        for u in units:
            j = u["i"] + k
            if not 0 <= j < len(S_arr[u["item"]]) or not np.isfinite(S_arr[u["item"]][j]):
                break
            vals.append(S_arr[u["item"]][j]); arrs.append(AR_arr[u["item"]][j])
        else:
            shifts.append(k); Tk.append(np.mean(vals)); prof.append(np.nanmean(np.array(arrs), axis=0))
    Tk, prof = np.array(Tk), np.array(prof)
    K = len(Tk)
    if K < 20:
        print(f"PERINGATAN: hanya {K} kalender digeser yang valid (data terlalu pendek untuk kalender ini); p-value kasar.")
    T = S.mean()
    p_drop = (1 + (Tk <= T).sum()) / (K + 1)
    p_two = (1 + (np.abs(Tk - Tk.mean()) >= abs(T - Tk.mean())).sum()) / (K + 1)
    boot = rng.choice(S, size=(args.boot, n)).mean(axis=1)
    lo, hi = np.percentile(boot, [5, 95])
    R, Tp = K, Tk

    # --- tabel per kejadian
    rows = []
    for u in units:
        seg = u["ar"][t >= 0]
        j = int(np.nanargmin(seg))
        rows.append({"item": u["item"], "event": u["event"], "mulai": u["start"], "tren_sebelum_%/hari": round(u["slope"], 2),
                     f"efek_{args.stat[0]}..{args.stat[1]}_%": round(pct(u["S"]), 1),
                     "titik_terendah_%": round(pct(seg[j]), 1), "hari_terendah": j})
    table = pd.DataFrame(rows)
    table.to_csv(out / "occurrences.csv", index=False)

    print(f"\n=== EVENT STUDY: '{args.event}' | item: {', '.join(series)} | {n} kejadian ===")
    print(f"Jendela efek: hari +{args.stat[0]} s/d +{args.stat[1]} dari mulai event. "
          f"Pembanding: {'tren hari -%d..-%d diekstrapolasi' % (-args.trend[0], -args.trend[1]) if args.detrend == 'slope' else 'rata-rata hari %d..%d' % tuple(args.base)}.")
    print(table.to_string(index=False))
    neg = int((S < 0).sum())
    print(f"\nEfek rata-rata  : {pct(T):+.1f}%   (median {pct(np.median(S)):+.1f}%)   interval 90% bootstrap {pct(lo):+.1f}% s/d {pct(hi):+.1f}%")
    print(f"Konsistensi tanda: {neg} dari {n} kejadian negatif")
    print(f"Plasebo ({R} kalender event digeser -{args.max_shift}..+{args.max_shift} hari): efek rata-rata biasa {pct(Tp.mean()):+.1f}% (sebaran 5-95%: {pct(np.percentile(Tp, 5)):+.1f}% s/d {pct(np.percentile(Tp, 95)):+.1f}%)")
    print(f"p-value (hanya turun): {p_drop:.3f}   |   dua arah: {p_two:.3f}")
    verdict = []
    if n < 4:
        verdict.append(f"Sampel kecil ({n} kejadian): hasil kasar. Tambahkan item lain atau tahun lain.")
    if p_drop < 0.05 and neg >= 0.75 * n:
        verdict.append("Bukti KUAT penurunan khas event: efeknya jarang muncul di tanggal acak dan arahnya konsisten.")
    elif p_drop < 0.10:
        verdict.append("Bukti LEMAH/SEDANG. Jangan dijadikan aturan trading sebelum diuji di item lain.")
    else:
        verdict.append("TIDAK ada bukti penurunan khas event yang melampaui kebetulan. Pola di chart bisa jadi sekadar tren/derau.")
    print("Kesimpulan      :", " ".join(verdict))
    print("Catatan: jendela dan batas ini sebaiknya ditetapkan SEBELUM melihat hasil; mencoba banyak jendela sampai ada yang bagus menggembungkan peluang kebetulan.")

    # --- ketahanan: item di tahun yang sama bergerak bersama, jadi sampel efektif adalah JUMLAH TAHUN, bukan jumlah baris
    by_year = {}
    for u in units:
        by_year.setdefault(u["start"].year, []).append(u["S"])
    print(f"\nPer tahun (rata-rata item): " + " | ".join(f"{y}: {pct(np.mean(v)):+.1f}%" for y, v in sorted(by_year.items())))
    print(f"Sampel efektif sebenarnya: {len(by_year)} tahun berbeda (bukan {n} kejadian), karena item di tahun yang sama saling terkait.")
    if len(by_year) >= 3:
        print("Uji ketahanan (membuang satu tahun):")
        for y in sorted(by_year):
            sub = [u for u in units if u["start"].year != y]
            p_sub = _shift_p([(u["item"], u["i"]) for u in sub], S_arr, args)
            ps = f"{p_sub:.3f}" if np.isfinite(p_sub) else "n/a"
            print(f"   tanpa {y}: efek rata-rata {pct(np.mean([u['S'] for u in sub])):+.1f}% | p turun = {ps} ({len(sub)} kejadian)")
        print("   -> Kalau efek hilang atau p melonjak begitu satu tahun dibuang, kesimpulannya bertumpu pada tahun itu saja.")
    steep = [u for u in units if abs(u["slope"]) >= 0.5]
    if steep:
        print("\nPERINGATAN tren curam sebelum event (>= 0,5%/hari): " + ", ".join(f"{u['item']} {u['start']} ({u['slope']:+.2f}%/hari)" for u in steep))
        print("   Mengekstrapolasi tren sebesar itu ke depan bisa membuat 'efek' tampak sangat besar hanya karena tren BERBALIK. Bandingkan dengan --detrend none.")

    # --- grafik profil
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    band = prof
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.fill_between(t, pct(np.nanpercentile(band, 5, axis=0)), pct(np.nanpercentile(band, 95, axis=0)), color="#94a3b8", alpha=0.35, label="plasebo 5-95% (kalender digeser)")
    for u in units:
        ax.plot(t, pct(u["ar"]), color="#f97316", alpha=0.25, lw=1)
    ax.plot(t, pct(np.nanmean(np.array([u["ar"] for u in units]), axis=0)), color="#ea580c", lw=2.5, label=f"rata-rata {n} kejadian event")
    ax.axvline(0, color="k", lw=1, ls="--"); ax.axhline(0, color="k", lw=0.5)
    ax.axvspan(args.stat[0], args.stat[1], color="#3b82f6", alpha=0.08, label="jendela uji")
    ax.set_xlabel("hari sejak mulai event"); ax.set_ylabel("% terhadap tren sebelum event")
    ax.set_title(f"'{args.event}' - {', '.join(series)} (p turun = {p_drop:.3f})"); ax.legend(loc="best", fontsize=8)
    fig.tight_layout(); fig.savefig(out / "event_profile.png", dpi=130); plt.close(fig)
    print(f"\nFile: {out/'event_profile.png'}, {out/'occurrences.csv'}")
    return 0


# --------------------------------------------------------------------------- daya uji
def _s_arrays(series: dict, args) -> dict:
    out = {}
    for it, lp in series.items():
        x = lp.to_numpy()
        out[it] = np.array([stat_of(ar_profile(x, i, args), args) for i in range(len(x))])
    return out


def _shift_p(unit_pos, S_arr, args) -> float:
    T = np.mean([S_arr[it][i] for it, i in unit_pos])
    Tk = []
    for k in range(-args.max_shift, args.max_shift + 1):
        if k == 0 or abs(k) < args.min_shift:
            continue
        vals = []
        for it, i in unit_pos:
            j = i + k
            if not 0 <= j < len(S_arr[it]) or not np.isfinite(S_arr[it][j]):
                break
            vals.append(S_arr[it][j])
        else:
            Tk.append(np.mean(vals))
    return (1 + (np.array(Tk) <= T).sum()) / (len(Tk) + 1) if len(Tk) >= 20 else np.nan


def power(series: dict, chosen: pd.DataFrame, args) -> int:
    """Seberapa besar penurunan yang BISA terdeteksi dari data ini? Menanam penurunan buatan (bentuk sama:
    turun hari +2..+12, pulih penuh hari +25) di deret ASLI pada kalender semu (kalender event digeser ke
    tempat acak), lalu mengukur seberapa sering uji menangkapnya. Menjawab: 'kalau hasilnya tidak
    signifikan, apakah itu karena memang tidak ada efek, atau karena datanya terlalu berisik?'"""
    rng = np.random.default_rng(args.seed)
    base = [(it, (ev["start_date"] - lp.index[0]).days) for it, lp in series.items()
            for _, ev in chosen.iterrows() if 0 <= (ev["start_date"] - lp.index[0]).days < len(lp)]
    if not base:
        sys.exit("Tidak ada kejadian event di dalam rentang data.")
    n_units = len(base)
    levels = [0.05, 0.10, 0.15, 0.20, 0.30]
    shape = np.zeros(args.post + 1)
    for t in range(2, min(26, args.post + 1)):
        shape[t] = 1.0 if t <= 12 else 1 - (t - 12) / 13

    print(f"\n=== DAYA UJI: '{args.event}' | item: {', '.join(series)} | {n_units} kejadian | {args.power_reps} ulangan per ukuran ===")
    print("Penurunan buatan ditanam di deret aslimu pada kalender semu; tabel = seberapa sering uji menangkapnya (p<0.05).\n")
    print("  penurunan  | terdeteksi p<0.05 | terdeteksi p<0.10")
    mde = None
    for dip in levels:
        d = -np.log(1 - dip)
        hit05 = hit10 = tried = 0
        for _ in range(args.power_reps):
            k = int(rng.integers(-args.max_shift, args.max_shift + 1))
            pos = [(it, i + k) for it, i in base]
            if any(not (args.trend[0] * -1 <= j < len(series[it]) - args.post - 1) for it, j in pos):
                continue
            mod = {}
            for it, lp in series.items():
                x = lp.copy()
                for it2, j in pos:
                    if it2 == it:
                        x.iloc[j:j + args.post + 1] -= d * shape
                mod[it] = x
            S_arr = _s_arrays(mod, args)
            if not all(np.isfinite(S_arr[it][j]) for it, j in pos):
                continue
            p = _shift_p(pos, S_arr, args)
            if np.isfinite(p):
                tried += 1
                hit05 += p < 0.05
                hit10 += p < 0.10
        if tried == 0:
            print(f"  -{dip*100:>3.0f}%      | (tidak ada kalender semu yang valid; data terlalu pendek)")
            continue
        r05, r10 = hit05 / tried, hit10 / tried
        print(f"  -{dip*100:>3.0f}%      | {r05*100:>10.0f}%       | {r10*100:>10.0f}%    ({tried} ulangan valid)")
        if mde is None and r05 >= 0.8:
            mde = dip
    print()
    if mde is None:
        print("Kesimpulan: bahkan penurunan 30% belum terdeteksi andal (>=80%). Dengan jumlah kejadian dan tingkat derau ini, "
              "hasil 'tidak signifikan' TIDAK berarti tidak ada efek. Tambahkan item atau tahun, atau perlebar jendela data.")
    else:
        print(f"Kesimpulan: penurunan terkecil yang terdeteksi andal (>=80%) kira-kira {mde*100:.0f}%. "
              f"Efek lebih kecil dari itu tidak akan terlihat dari data ini, jadi 'tidak signifikan' berarti 'tidak ada efek sebesar itu atau lebih'.")
    return 0


# --------------------------------------------------------------------------- eksplorasi musiman
def explore(series: dict, out: Path) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for it, lp in series.items():
        dev = (lp - lp.rolling(91, center=True, min_periods=45).median()) * 100
        iso = dev.index.isocalendar()
        wk = dev.groupby([iso.year.values, iso.week.values]).mean().unstack(0).reindex(range(1, 54))
        fig, ax = plt.subplots(figsize=(12, 3 + 0.4 * wk.shape[1]))
        im = ax.imshow(wk.T.values, aspect="auto", cmap="RdBu", vmin=-25, vmax=25)
        ax.set_yticks(range(wk.shape[1])); ax.set_yticklabels(wk.columns)
        ax.set_xticks(range(0, 53, 4)); ax.set_xticklabels(range(1, 54, 4)); ax.set_xlabel("minggu ISO")
        ax.set_title(f"{it}: simpangan harga dari tren 91 hari (%) per minggu dan tahun (biru = di bawah tren)")
        fig.colorbar(im, ax=ax); fig.tight_layout(); fig.savefig(out / f"explore_{it}.png", dpi=130); plt.close(fig)
        stats = pd.DataFrame({"rata2_%": wk.mean(axis=1), "tahun_data": wk.notna().sum(axis=1), "tahun_di_bawah_tren": (wk < 0).sum(axis=1)})
        low = stats[stats["tahun_data"] >= 3].sort_values("rata2_%").head(6)
        print(f"\n[{it}] 6 minggu dengan simpangan rata-rata paling negatif (minimal 3 tahun data):")
        print(low.round(1).to_string())
        print(f"Peta: {out / f'explore_{it}.png'}")
    print("\nCatatan: ini untuk MENCARI kandidat musim, bukan bukti. Uji kandidatnya dengan --event setelah tanggal eventnya diisi.")
    return 0


def parse():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", required=True, type=lambda s: [x.strip() for x in s.split(",") if x.strip()])
    ap.add_argument("--event", default="", help="kata kunci nama event (tidak peka huruf besar/kecil)")
    ap.add_argument("--explore", action="store_true", help="peta musiman tanpa kalender event")
    ap.add_argument("--power", action="store_true", help="ukur seberapa kecil penurunan yang bisa dideteksi dari data ini")
    ap.add_argument("--power-reps", type=int, default=20, help="ulangan per ukuran penurunan untuk --power")
    ap.add_argument("--csv", help="CSV harga (item_name,date,median_price,total_volume) sebagai pengganti Supabase")
    ap.add_argument("--events-csv", help="CSV event (name,start_date,end_date)")
    ap.add_argument("--pre", type=int, default=30)
    ap.add_argument("--post", type=int, default=45)
    ap.add_argument("--stat", type=int, nargs=2, default=[3, 21], metavar=("DARI", "SAMPAI"), help="jendela efek (hari sejak mulai)")
    ap.add_argument("--detrend", choices=["slope", "none"], default="slope",
                    help="slope = ekstrapolasi tren sebelum event (disarankan; harga punya tren besar); none = rata-rata baseline")
    ap.add_argument("--trend", type=int, nargs=2, default=[-90, -8], metavar=("DARI", "SAMPAI"), help="jendela untuk menaksir tren")
    ap.add_argument("--base", type=int, nargs=2, default=[-30, -8], metavar=("DARI", "SAMPAI"), help="jendela baseline untuk --detrend none")
    ap.add_argument("--max-shift", type=int, default=400, help="geser kalender event sejauh +-N hari untuk membangun plasebo")
    ap.add_argument("--min-shift", type=int, default=0, help="abaikan geseran lebih kecil dari N hari (0 = pakai semua; paling jujur)")
    ap.add_argument("--boot", type=int, default=5000, help="jumlah ulangan bootstrap untuk interval kepercayaan")
    ap.add_argument("--min-volume", type=int, default=5, help="hari dengan total postingan lebih sedikit dianggap kosong")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="analysis_out")
    a = ap.parse_args()
    if a.explore and (a.power or a.event):
        ap.error("--explore tidak bisa digabung dengan --event / --power (--explore hanya membuat peta musiman). Jalankan terpisah.")
    if not a.explore and not a.event:
        ap.error("isi --event KATA_KUNCI (atau pakai --explore)")
    return a


if __name__ == "__main__":
    sys.exit(run(parse()))
