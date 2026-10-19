/**
 * Format a cent amount as a US dollar string.
 * e.g. 42300 → "$423"
 */
export function formatCents(cents: number): string {
  return (
    '$' +
    (cents / 100).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  )
}

/** `0.12.0` -> `v0.12.0`; non-release strings such as `dev` are shown as-is. */
export function formatVersion(version: string): string {
  return /^\d/.test(version) ? `v${version}` : version
}
