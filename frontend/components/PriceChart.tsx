"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { supabase } from "@/lib/supabase";

// shadcn: npx shadcn@latest add select toggle-group

type Range = "7D" | "30D" | "1Y" | "ALL";
const RANGE_DAYS: Record<Range, number | null> = { "7D": 7, "30D": 30, "1Y": 365, ALL: null };

type SeriesKey = "sell" | "buy" | "combined";

type Point = {
  date: string;
  sell: number | null;     // median harga penjual
  buy: number | null;      // median harga pembeli
  combined: number;        // median gabungan
  sellVol: number;
  buyVol: number;
  volume: number;
  min: number;
  max: number;
};

// Biru vs oranye tetap mudah dibedakan untuk buta warna; gabungan memakai warna teks.
const SERIES: { key: SeriesKey; label: string; color: string; dashed?: boolean }[] = [
  { key: "sell", label: "Penjual (sell)", color: "#f97316" },
  { key: "buy", label: "Pembeli (buy)", color: "#3b82f6" },
  { key: "combined", label: "Gabungan", color: "currentColor", dashed: true },
];

// Harga disimpan dalam BGL. Di bawah 1 BGL tampilkan dalam WL / DL agar terbaca.
function fmtPrice(bgl: number | null): string {
  if (bgl == null) return "–";
  if (bgl >= 1) return `${+bgl.toFixed(2)} BGL`;
  const wl = bgl * 10_000;
  return wl >= 100 ? `${+(wl / 100).toFixed(1)} DL` : `${Math.round(wl)} WL`;
}

function fmtDate(iso: string, long = false) {
  return new Date(iso + "T00:00:00").toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    ...(long ? { year: "numeric" } : {}),
  });
}

// Supabase membatasi 1000 baris per request, jadi ambil per halaman.
async function fetchPrices(item: string, range: Range): Promise<Point[]> {
  const days = RANGE_DAYS[range];
  const from = days
    ? new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
    : null;

  const PAGE = 1000;
  const rows: any[] = [];
  for (let offset = 0; ; offset += PAGE) {
    let q = supabase
      .from("daily_item_prices")
      .select(
        "date, median_price, min_price, max_price, total_volume, buy_median, sell_median, buy_volume, sell_volume"
      )
      .eq("item_name", item)
      .order("date", { ascending: true })
      .range(offset, offset + PAGE - 1);
    if (from) q = q.gte("date", from);
    const { data, error } = await q;
    if (error) throw error;
    rows.push(...data);
    if (data.length < PAGE) break;
  }

  const num = (v: unknown) => (v == null ? null : Number(v));
  return rows.map((r) => ({
    date: r.date,
    sell: num(r.sell_median),
    buy: num(r.buy_median),
    combined: Number(r.median_price),
    sellVol: r.sell_volume ?? 0,
    buyVol: r.buy_volume ?? 0,
    volume: r.total_volume,
    min: Number(r.min_price),
    max: Number(r.max_price),
  }));
}

// Harga terakhir + perubahan % dari titik pertama yang punya data.
function trend(data: Point[], key: SeriesKey) {
  const vals = data.map((d) => d[key]).filter((v): v is number => v != null);
  if (!vals.length) return null;
  const first = vals[0];
  const last = vals[vals.length - 1];
  return { last, change: vals.length > 1 ? ((last - first) / first) * 100 : null };
}

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p: Point = payload[0].payload;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm shadow-sm">
      <div className="font-medium">{fmtDate(p.date, true)}</div>
      <div className="mt-1 grid grid-cols-[auto_auto_auto] gap-x-4 text-muted-foreground">
        {SERIES.map((s) => (
          <div key={s.key} className="contents">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="text-right text-foreground">{fmtPrice(p[s.key])}</span>
            <span className="text-right">
              {s.key === "sell" ? p.sellVol : s.key === "buy" ? p.buyVol : p.volume} post
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        Rentang gabungan {fmtPrice(p.min)} – {fmtPrice(p.max)}
      </div>
    </div>
  );
}

export default function PriceChart() {
  const [items, setItems] = useState<string[]>([]);
  const [item, setItem] = useState<string>("");
  const [range, setRange] = useState<Range>("30D");
  const [data, setData] = useState<Point[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Daftar item dari view item_list (diurutkan dari yang paling ramai).
  useEffect(() => {
    supabase
      .from("item_list")
      .select("item_name")
      .then(({ data, error }) => {
        if (error) return setError(error.message);
        const names = (data ?? []).map((d) => d.item_name as string);
        setItems(names);
        if (names.length) setItem(names[0]);
        else setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!item) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPrices(item, range)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message ?? "Gagal memuat data"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [item, range]);

  const stats = useMemo(
    () => SERIES.map((s) => ({ ...s, t: trend(data, s.key) })),
    [data]
  );

  return (
    <section className="w-full max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Select value={item} onValueChange={setItem} disabled={!items.length}>
          <SelectTrigger className="w-52 uppercase">
            <SelectValue placeholder="Pilih item" />
          </SelectTrigger>
          <SelectContent>
            {items.map((name) => (
              <SelectItem key={name} value={name} className="uppercase">
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <ToggleGroup
          type="single"
          variant="outline"
          value={range}
          onValueChange={(v) => v && setRange(v as Range)}
        >
          {(Object.keys(RANGE_DAYS) as Range[]).map((r) => (
            <ToggleGroupItem key={r} value={r} aria-label={`Rentang ${r}`}>
              {r}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {data.length > 0 && !loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {stats.map((s) => (
            <div key={s.key}>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
                {s.label}
              </div>
              <div className="text-2xl font-semibold tabular-nums">
                {s.t ? fmtPrice(s.t.last) : "–"}
              </div>
              {s.t?.change != null && (
                <div
                  className={`text-sm tabular-nums ${
                    s.t.change >= 0 ? "text-emerald-600" : "text-red-600"
                  }`}
                >
                  {s.t.change >= 0 ? "+" : ""}
                  {s.t.change.toFixed(1)}% dalam {range}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="h-[380px] w-full text-foreground">
        {error ? (
          <p className="grid h-full place-items-center text-sm text-red-600">
            Data tidak bisa dimuat: {error}
          </p>
        ) : loading ? (
          <p className="grid h-full place-items-center text-sm text-muted-foreground">
            Memuat data…
          </p>
        ) : data.length === 0 ? (
          <p className="grid h-full place-items-center text-sm text-muted-foreground">
            Belum ada data untuk rentang ini. Coba pilih rentang yang lebih panjang.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="currentColor" strokeOpacity={0.1} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => fmtDate(d, range === "1Y" || range === "ALL")}
                tick={{ fontSize: 12 }}
                tickLine={false}
                minTickGap={32}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={56}
                tickFormatter={(v) => `${+v.toFixed(2)}`}
                label={{ value: "BGL", angle: -90, position: "insideLeft", fontSize: 12 }}
              />
              <Tooltip content={<ChartTooltip />} />
              <Legend verticalAlign="top" height={28} iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
              {SERIES.map((s) => (
                <Line
                  key={s.key}
                  name={s.label}
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={s.dashed ? 1.5 : 2}
                  strokeDasharray={s.dashed ? "5 4" : undefined}
                  connectNulls
                  dot={data.length <= 31}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}