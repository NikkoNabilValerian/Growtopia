import { supabase } from "@/lib/supabase";
import { toPoints, type EventRow, type Point, type SignalRow } from "@/lib/analytics";

export type ItemInfo = { name: string; label: string };

/** Daftar item untuk dropdown. Memakai kolom label bila sudah dimigrasi, kalau belum pakai nama item. */
export async function fetchItems(): Promise<ItemInfo[]> {
  let res: any = await supabase.from("item_list").select("item_name, label");
  if (res.error) res = await supabase.from("item_list").select("item_name"); // sebelum migrasi 002
  if (res.error) throw new Error(res.error.message);
  return (res.data ?? []).map((d: any) => ({
    name: d.item_name as string,
    label: (d.label as string | undefined) ?? String(d.item_name).toUpperCase(),
  }));
}

/** Seluruh riwayat satu item. Supabase membatasi 1000 baris per request, jadi ambil per halaman.
 *  select("*") agar kolom baru (penulis unik, dll.) otomatis ikut tanpa mengubah kode ini. */
export async function fetchPrices(item: string): Promise<Point[]> {
  const PAGE = 1000;
  const rows: any[] = [];
  for (let offset = 0; ; offset += PAGE) {
    const { data, error } = await supabase
      .from("daily_item_prices")
      .select("*")
      .eq("item_name", item)
      .order("date", { ascending: true })
      .range(offset, offset + PAGE - 1);
    if (error) throw new Error(error.message);
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE) break;
  }
  return toPoints(rows);
}

/** Tabel opsional: kalau belum ada / kosong, kembalikan daftar kosong tanpa error. */
export async function fetchEvents(): Promise<EventRow[]> {
  try {
    const { data, error } = await supabase.from("events").select("*").order("start_date");
    return error ? [] : ((data ?? []) as EventRow[]);
  } catch {
    return [];
  }
}

export async function fetchSignals(item: string): Promise<SignalRow[]> {
  try {
    const { data, error } = await supabase
      .from("item_signals")
      .select("date, predicted, resid_z, signal, reason")
      .eq("item_name", item)
      .order("date", { ascending: true })
      .limit(5000);
    return error ? [] : ((data ?? []) as SignalRow[]);
  } catch {
    return [];
  }
}