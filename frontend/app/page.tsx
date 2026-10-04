import Dashboard from "@/components/Dashboard";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold">Growtopia Price Tracker</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Pergerakan harga harian item dari promosi jual-beli di Discord, lengkap dengan indikator untuk analisis
          investasi.
        </p>
      </header>
      <Dashboard />
    </main>
  );
}