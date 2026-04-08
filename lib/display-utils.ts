/**
 * Extracts just the 4-digit year from an ISO date string.
 * Returns "—" for null/undefined input.
 */
export function formatYearOfBirth(
  dob: string | null | undefined
): string {
  if (!dob) return "\u2014";
  return new Date(dob).getFullYear().toString();
}
