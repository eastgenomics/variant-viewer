export function formatYearOfBirth(dob: string | null | undefined): string {
  if (!dob) return "\u2014";
  const match = dob.match(/^(\d{4})(?:-|$)/);
  return match ? match[1] : "\u2014";
}

export function formatGnomadAf(af: number | null): string {
  if (af == null) return "absent";
  return af < 0.0001 ? af.toExponential(2) : af.toFixed(4);
}

export function formatRevel(v: number | null): string {
  return v == null ? "\u2014" : v.toFixed(3);
}

export function formatSpliceAi(v: number | null): string {
  return v == null ? "\u2014" : v.toFixed(3);
}

export function gnomadAfClass(af: number | null): string {
  return af != null && af > 0.01 ? "text-amber-600" : "text-gray-700";
}

export function revelClass(v: number | null): string {
  if (v == null) return "text-gray-700";
  if (v >= 0.7) return "text-red-600";
  if (v <= 0.4) return "text-green-700";
  return "text-gray-700";
}

export function spliceAiClass(v: number | null): string {
  return v != null && v >= 0.5 ? "text-orange-600" : "text-gray-700";
}
