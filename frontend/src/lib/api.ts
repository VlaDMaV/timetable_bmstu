const BASE = process.env.NEXT_PUBLIC_API_BASE;

export async function api<T>(path: string) {
  if (!BASE) throw new Error("NEXT_PUBLIC_API_BASE is not set");
  const res = await fetch(`${BASE}${path}`, {
    // серверный запрос без кэша, чтобы всегда получать свежий список
    cache: "no-store",
    headers: { accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}