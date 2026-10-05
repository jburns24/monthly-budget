import type { Frequency } from '../types/recurring'

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** Next occurrence after `dateStr` (YYYY-MM-DD); month/year steps clamp to the month end. */
export function nextOccurrence(dateStr: string, frequency: Frequency): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  if (frequency === 'weekly' || frequency === 'biweekly') {
    const next = new Date(Date.UTC(y, m - 1, d + (frequency === 'weekly' ? 7 : 14)))
    return `${next.getUTCFullYear()}-${pad(next.getUTCMonth() + 1)}-${pad(next.getUTCDate())}`
  }
  const monthsToAdd = frequency === 'monthly' ? 1 : 12
  const targetIndex = m - 1 + monthsToAdd
  const year = y + Math.floor(targetIndex / 12)
  const month = targetIndex % 12
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  return `${year}-${pad(month + 1)}-${pad(Math.min(d, lastDay))}`
}
