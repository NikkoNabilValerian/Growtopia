import PriceChart from "@/components/PriceChart";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Growtopia Price Tracker</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Harga median harian dari promosi jual-beli di Discord. Area tipis menunjukkan
          rentang harga terendah sampai tertinggi.
        </p>
      </header>
      <PriceChart />
    </main>
  );
}