import { createClient } from "@supabase/supabase-js";

// Hanya anon key di frontend. RLS membatasi akses ke SELECT saja.
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);