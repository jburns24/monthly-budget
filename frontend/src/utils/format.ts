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
