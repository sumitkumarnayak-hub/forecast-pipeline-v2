/** Parse API / cache values that may arrive as strings into finite numbers. */
export function coerceNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const n = Number(v.trim().replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  return null;
}
