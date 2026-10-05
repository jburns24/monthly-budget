import { describe, it, expect } from 'vitest'
import { nextOccurrence } from '../utils/recurrence'

describe('nextOccurrence', () => {
  it('adds 7 and 14 days', () => {
    expect(nextOccurrence('2026-10-04', 'weekly')).toBe('2026-10-11')
    expect(nextOccurrence('2026-10-25', 'biweekly')).toBe('2026-11-08')
  })

  it('adds a month and clamps to the month end', () => {
    expect(nextOccurrence('2026-01-15', 'monthly')).toBe('2026-02-15')
    expect(nextOccurrence('2026-01-31', 'monthly')).toBe('2026-02-28')
    expect(nextOccurrence('2026-12-10', 'monthly')).toBe('2027-01-10')
  })

  it('adds a year and handles leap days', () => {
    expect(nextOccurrence('2026-06-01', 'yearly')).toBe('2027-06-01')
    expect(nextOccurrence('2028-02-29', 'yearly')).toBe('2029-02-28')
  })
})
