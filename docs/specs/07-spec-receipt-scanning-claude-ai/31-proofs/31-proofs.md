# FIX-REVIEW-31 — ReceiptCaptureDialog responsive placement (mobile bottom-sheet)

**Task**: FIX-REVIEW-31 (review ISSUE-6, Category C spec compliance)
**Spec**: docs/specs/07-spec-receipt-scanning-claude-ai/07-spec-receipt-scanning-claude-ai.md §Design Considerations
**Branch**: feature/07-receipt-scanning-claude-ai
**Worker**: worker-5
**Model**: opus
**Timestamp**: 2026-04-19T07:19:40Z

## Summary

Spec §Design Considerations requires `ReceiptCaptureDialog` to use Chakra
`Dialog` `placement="bottom"` on mobile breakpoints (PRD §6.4 thumb-zone
guidance) and center placement on larger screens. The original
implementation hardcoded `placement="center"` at every breakpoint, violating
the bottom-sheet requirement for mobile users.

Fix: replace the scalar `placement="center"` with the Chakra v3 responsive
prop form `placement={{ base: 'bottom', md: 'center' }}`. No other behavior
changes; all 22 pre-existing tests still pass, and one new test asserts the
responsive object is forwarded to `DialogRoot`.

## Files Changed

- `frontend/src/components/expenses/ReceiptCaptureDialog.tsx` — `DialogRoot`
  placement is now a responsive object.
- `frontend/src/__tests__/ReceiptCaptureDialog.test.tsx` — adds one new test
  under `describe('responsive placement')` that spies on the Chakra
  `DialogRoot` export and asserts the component forwards
  `{ base: 'bottom', md: 'center' }`.

## Proof Artifacts

| # | Type | File | Status |
|---|------|------|--------|
| 1 | test | `31-01-test.txt` | PASS — 23/23 tests, including new responsive-placement test |
| 2 | file | `31-02-file.txt` | PASS — source confirms responsive placement prop |
| 3 | cli  | `31-03-tsc.txt`  | PASS — `tsc --noEmit` clean |

## Verification Commands

```bash
# Lint / typecheck / tests (frontend)
cd frontend && npm run lint && npx tsc --noEmit && npm run test:run -- ReceiptCaptureDialog
```

## Spec Traceability

- Spec line 203: "ReceiptCaptureDialog must meet PRD §6.4 — 44px+ touch
  targets, thumb-zone primary actions, bottom-sheet style (Chakra `Dialog`
  with `placement='bottom'` on mobile breakpoints)."
- Review ISSUE-6 (Category C): `placement="center"` at every breakpoint;
  recommended fix `placement={{ base: 'bottom', md: 'center' }}`.
