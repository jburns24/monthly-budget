# T04 Proof Summary — Frontend Capture Dialog (Rollup)

**Task**: T04 — Frontend Capture Dialog
**Status**: COMPLETED
**Date**: 2026-04-19

## Sub-Task Completion Checklist

| Sub-Task | Subject | Commit | Status |
|----------|---------|--------|--------|
| T04.1 (#18) | Frontend types: receipts + Expense extension | f821f88 | ✓ DONE |
| T04.2 (#19) | api/receipts.ts (upload + CRUD helpers) | b37cb12 | ✓ DONE |
| T04.3 (#20) | useOnlineStatus hook + test | (worker-4) | ✓ DONE |
| T04.4 (#21) | ReceiptCaptureDialog component (Phase state machine) | 881a2c4 | ✓ DONE |
| T04.5 (#22) | Scan Receipt CTA integration (offline-aware) | 3dd22c0 | ✓ DONE |

## Deliverables Summary

### Types (`frontend/src/types/receipts.ts`)
- `ReceiptStatus`, `Receipt`, `ReceiptUploadResponse` interfaces
- `Expense` extended with `receipt_id`, `receipt_status`

### API (`frontend/src/api/receipts.ts`)
- `uploadReceipt`, `getReceipts`, `getReceipt`, `deleteReceipt`, `retryReceipt`

### Hook (`frontend/src/hooks/useOnlineStatus.ts`)
- `useOnlineStatus()` — wraps `navigator.onLine` + online/offline events

### Component (`frontend/src/components/expenses/ReceiptCaptureDialog.tsx`)
- Phase state machine: `idle → preview → uploading → reviewing → done`
- react-dropzone + browser-image-compression + TanStack useMutation
- Error-to-toast mapping (422/429/503/413/415)
- Needs-review badge, category override

### FAB (`frontend/src/components/expenses/FAB.tsx`)
- Scan Receipt button (`data-testid="fab-scan-receipt"`) above Add Expense FAB
- `disabled={!isOnline}` via `useOnlineStatus()`
- Chakra UI v3 Tooltip: "Receipt scanning requires a network connection."

### Tests
- `ReceiptCaptureDialog.test.tsx` — 22 tests (5 Phase describe blocks)
- `FAB.test.tsx` — 7 tests (online/offline, opens dialogs)
- `useOnlineStatus.test.ts` — 4 tests (worker-4)

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T04-01-test.txt | vitest (194 tests / 23 files) | PASS |
| T04-02-tsc.txt | tsc --noEmit | PASS |
