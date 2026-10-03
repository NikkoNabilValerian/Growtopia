"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
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

type Point = {
  date: string;
  median: number;
  avg: number;
  min: number;
  max: number;
  volume: number;
  band: [number, number]; // rentang min-max untuk area
};

// Harga disimpan dalam BGL. Di bawah 1 BGL tampilkan dalam WL / DL agar terbaca.
function fmtPrice(bgl: number): string {
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
      .select("date, median_price, avg_price, min_price, max_price, total_volume")
      .eq("item_name", item)
      .order("date", { ascending: true })
      .range(offset, offset + PAGE - 1);
    if (from) q = q.gte("date", from);
    const { data, error } = await q;
    if (error) throw error;
    rows.push(...data);
    if (data.length < PAGE) break;
  }

  return rows.map((r) => ({
    date: r.date,
    median: Number(r.median_price),
    avg: Number(r.avg_price),
    min: Number(r.min_price),
    max: Number(r.max_price),
    volume: r.total_volume,
    band: [Number(r.min_price), Number(r.max_price)],
  }));
}

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p: Point = payload[0].payload;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm shadow-sm">
      <div className="font-medium">{fmtDate(p.date, true)}</div>
      <div className="mt-1 grid grid-cols-[auto_auto] gap-x-4 text-muted-foreground">
        <span>Median</span><span className="text-right text-foreground">{fmtPrice(p.median)}</span>
        <span>Rata-rata</span><span className="text-right">{fmtPrice(p.avg)}</span>
        <span>Rentang</span><span className="text-right">{fmtPrice(p.min)} – {fmtPrice(p.max)}</span>
        <span>Postingan</span><span className="text-right">{p.volume}</span>
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

  const summary = useMemo(() => {
    if (data.length < 2) return null;
    const first = data[0].median;
    const last = data[data.length - 1].median;
    return { last, change: ((last - first) / first) * 100 };
  }, [data]);

  return (
    <section className="w-full max-w-4xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
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
          {summary && (
            <p className="mt-3 text-3xl font-semibold tabular-nums">
              {fmtPrice(summary.last)}
              <span
                className={`ml-3 text-base font-normal ${
                  summary.change >= 0 ? "text-emerald-600" : "text-red-600"
                }`}
              >
                {summary.change >= 0 ? "+" : ""}
                {summary.change.toFixed(1)}% dalam {range}
              </span>
            </p>
          )}
        </div>

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

      <div className="h-[380px] w-full text-primary">
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
              {/* Area tipis = rentang harga terendah-tertinggi hari itu */}
              <Area
                dataKey="band"
                stroke="none"
                fill="currentColor"
                fillOpacity={0.12}
                isAnimationActive={false}
              />
              <Line
                dataKey="median"
                stroke="currentColor"
                strokeWidth={2}
                dot={data.length <= 31}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}