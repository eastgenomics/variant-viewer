/**
 * Extracts just the 4-digit year from an ISO date string.
 * Returns "—" for null/undefined input.
 */
export function formatYearOfBirth(
  dob: string | null | undefined
): string {
  if (!dob) return "\u2014";
  const match = dob.match(/^(\d{4})(?:-|$)/);
  return match ? match[1] : "\u2014";
}
