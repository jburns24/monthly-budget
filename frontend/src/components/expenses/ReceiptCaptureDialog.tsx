import { useCallback, useReducer, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import imageCompression from 'browser-image-compression'
import {
  Box,
  Button,
  Image,
  Input,
  NativeSelectField,
  NativeSelectRoot,
  Spinner,
  Stack,
  Text,
} from '@chakra-ui/react'
import {
  DialogBackdrop,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogPositioner,
  DialogRoot,
  DialogTitle,
} from '@chakra-ui/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { uploadReceipt } from '../../api/receipts'
import { getCategories } from '../../api/categories'
import { getExpense, updateExpense } from '../../api/expenses'
import { toaster } from '../ui/toaster'
import type { ReceiptUploadResponse } from '../../types/receipts'
import type { ExpenseUpdate } from '../../types/expenses'

const COMPRESSION_OPTIONS = { maxSizeMB: 1.5, maxWidthOrHeight: 2400, useWebWorker: true }
const MAX_SIZE = 5 * 1024 * 1024

export type Phase = 'idle' | 'preview' | 'uploading' | 'reviewing' | 'done'

interface State {
  phase: Phase
  file: File | null
  previewUrl: string | null
  uploadResponse: ReceiptUploadResponse | null
  categoryId: string
  /** Empty until the user edits the date; the persisted value is the default. */
  expenseDate: string
}

type Action =
  | { type: 'FILE_SELECTED'; file: File; previewUrl: string }
  | { type: 'UPLOAD_START' }
  | { type: 'UPLOAD_SUCCESS'; response: ReceiptUploadResponse }
  | { type: 'UPLOAD_FAILED' }
  | { type: 'SET_CATEGORY'; categoryId: string }
  | { type: 'SET_DATE'; expenseDate: string }
  | { type: 'CONFIRM' }
  | { type: 'RESET' }

const initialState: State = {
  phase: 'idle',
  file: null,
  previewUrl: null,
  uploadResponse: null,
  categoryId: '',
  expenseDate: '',
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'FILE_SELECTED':
      return { ...state, phase: 'preview', file: action.file, previewUrl: action.previewUrl }
    case 'UPLOAD_START':
      return { ...state, phase: 'uploading' }
    case 'UPLOAD_SUCCESS':
      return { ...state, phase: 'reviewing', uploadResponse: action.response }
    case 'UPLOAD_FAILED':
      return { ...state, phase: 'preview' }
    case 'SET_CATEGORY':
      return { ...state, categoryId: action.categoryId }
    case 'SET_DATE':
      return { ...state, expenseDate: action.expenseDate }
    case 'CONFIRM':
      return { ...state, phase: 'done' }
    case 'RESET':
      if (state.previewUrl) URL.revokeObjectURL(state.previewUrl)
      return { ...initialState }
    default:
      return state
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  '409': 'Create a category before scanning receipts.',
  '422': "That doesn't look like a receipt. Try another image.",
  '429': 'Daily upload limit reached.',
  '503': 'Receipt service unavailable. Try again or enter manually.',
  '413': 'Image too large (max 5MB).',
  '415': 'Unsupported format — use JPEG, PNG, WebP, or HEIC.',
}

interface ReceiptCaptureDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
}

function formatCents(cents: number | null): string {
  if (cents == null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

export default function ReceiptCaptureDialog({
  open,
  onOpenChange,
  familyId,
}: ReceiptCaptureDialogProps) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const queryClient = useQueryClient()

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
    enabled: open,
  })

  const mutation = useMutation({
    mutationFn: async (file: File) => {
      const compressed = await imageCompression(file, COMPRESSION_OPTIONS)
      return uploadReceipt(familyId, compressed as File)
    },
    onSuccess: (response) => {
      dispatch({ type: 'UPLOAD_SUCCESS', response })
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      queryClient.invalidateQueries({ queryKey: ['receipts', familyId] })
    },
    onError: (error: Error) => {
      dispatch({ type: 'UPLOAD_FAILED' })
      const msg = ERROR_MESSAGES[error.message] ?? 'Upload failed. Please try again.'
      toaster.create({ title: 'Upload failed', description: msg, type: 'error', duration: 5000 })
    },
  })

  // The upload already created the Expense, but the response carries only its
  // id — we need the persisted date, category, and updated_at (for the
  // optimistic-locking token) to seed the review fields and to tell an actual
  // edit apart from an untouched default.
  const expenseId = state.uploadResponse?.expense_id ?? null
  const { data: expense } = useQuery({
    queryKey: ['expense', familyId, expenseId],
    queryFn: () => getExpense(familyId, expenseId!),
    enabled: state.phase === 'reviewing' && expenseId != null,
  })

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!expense) return
      const patch: ExpenseUpdate = { expected_updated_at: expense.updated_at }
      let dirty = false
      if (state.expenseDate && state.expenseDate !== expense.expense_date) {
        patch.expense_date = state.expenseDate
        dirty = true
      }
      if (state.categoryId && state.categoryId !== expense.category.id) {
        patch.category_id = state.categoryId
        dirty = true
      }
      if (!dirty) return
      await updateExpense(familyId, expense.id, patch)
    },
    onSuccess: () => {
      dispatch({ type: 'CONFIRM' })
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      queryClient.invalidateQueries({ queryKey: ['receipts', familyId] })
    },
    onError: () => {
      toaster.create({
        title: 'Could not save changes',
        description: 'Your edits were not saved. Try again.',
        type: 'error',
        duration: 5000,
      })
    },
  })

  const [dropError, setDropError] = useState<string | null>(null)

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (!file) return
    setDropError(null)
    const previewUrl = URL.createObjectURL(file)
    dispatch({ type: 'FILE_SELECTED', file, previewUrl })
  }, [])

  const onDropRejected = useCallback((fileRejections: { errors: { code: string }[] }[]) => {
    const codes = fileRejections.flatMap((r) => r.errors.map((e) => e.code))
    if (codes.includes('file-too-large')) {
      setDropError('Image too large (max 5MB).')
    } else if (codes.includes('file-invalid-type')) {
      setDropError('Unsupported format — use JPEG, PNG, WebP, or HEIC.')
    } else {
      setDropError('File could not be used.')
    }
  }, [])

  const { getRootProps, getInputProps } = useDropzone({
    accept: {
      'image/jpeg': [],
      'image/png': [],
      'image/webp': [],
      'image/heic': [],
      'image/heif': [],
    },
    maxSize: MAX_SIZE,
    maxFiles: 1,
    onDropAccepted: onDrop,
    onDropRejected,
    disabled: state.phase !== 'idle',
  })

  function handleUpload() {
    if (!state.file) return
    dispatch({ type: 'UPLOAD_START' })
    mutation.mutate(state.file)
  }

  function handleClose() {
    dispatch({ type: 'RESET' })
    onOpenChange(false)
  }

  const receipt = state.uploadResponse?.receipt
  // Default to what was persisted, not to the first category: the upload already
  // picked a suggested category, and defaulting to categories[0] would silently
  // overwrite a good suggestion on Confirm.
  const effectiveCategoryId = state.categoryId || expense?.category.id || ''
  // parsed_date is null when Claude could not read a date; the backend fell back
  // to today, which is what the expense actually holds.
  const effectiveDate = state.expenseDate || expense?.expense_date || receipt?.parsed_date || ''
  const fieldsDisabled = expense == null || confirmMutation.isPending

  return (
    <DialogRoot
      open={open}
      onOpenChange={(e) => !e.open && handleClose()}
      placement={{ base: 'bottom', md: 'center' }}
    >
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent data-testid="receipt-capture-dialog">
          <DialogHeader>
            <DialogTitle>Scan Receipt</DialogTitle>
          </DialogHeader>

          <DialogBody>
            {state.phase === 'idle' && (
              <Box
                {...getRootProps()}
                border="2px dashed"
                borderColor="gray.300"
                borderRadius="md"
                p={8}
                textAlign="center"
                cursor="pointer"
                data-testid="receipt-dropzone"
              >
                <input
                  {...getInputProps()}
                  capture="environment"
                  data-testid="receipt-file-input"
                />
                <Text color="gray.500">Drag & drop a receipt image, or click to select</Text>
                <Text fontSize="xs" color="gray.400" mt={2}>
                  JPEG, PNG, WebP, or HEIC — max 5MB
                </Text>
                {dropError && (
                  <Text
                    data-testid="receipt-drop-error"
                    role="alert"
                    mt={3}
                    color="red.600"
                    fontSize="sm"
                  >
                    {dropError}
                  </Text>
                )}
              </Box>
            )}

            {state.phase === 'preview' && state.previewUrl && (
              <Stack gap={4} align="center">
                <Image
                  src={state.previewUrl}
                  alt="Receipt preview"
                  maxH="300px"
                  objectFit="contain"
                  data-testid="receipt-preview-image"
                />
                <Text fontSize="sm" color="gray.600">
                  {state.file?.name}
                </Text>
              </Stack>
            )}

            {state.phase === 'uploading' && (
              <Stack align="center" gap={4} py={8} data-testid="receipt-uploading">
                <Spinner size="xl" />
                <Text>Processing receipt…</Text>
              </Stack>
            )}

            {state.phase === 'reviewing' && receipt && (
              <Stack gap={4} data-testid="receipt-reviewing">
                {state.uploadResponse?.needs_edit && (
                  <Box
                    bg="yellow.100"
                    color="yellow.800"
                    px={3}
                    py={1}
                    borderRadius="md"
                    fontSize="sm"
                    fontWeight="medium"
                    data-testid="receipt-needs-review-badge"
                  >
                    Needs review
                  </Box>
                )}
                <Stack gap={1}>
                  <Text fontWeight="medium" fontSize="sm">
                    Merchant
                  </Text>
                  <Text data-testid="receipt-merchant">{receipt.parsed_merchant ?? '—'}</Text>
                </Stack>
                <Stack gap={1}>
                  <Text fontWeight="medium" fontSize="sm">
                    Amount
                  </Text>
                  <Text data-testid="receipt-amount">
                    {formatCents(receipt.parsed_total_cents)}
                  </Text>
                </Stack>
                <Stack gap={1}>
                  <Text fontWeight="medium" fontSize="sm">
                    Date
                  </Text>
                  <Input
                    type="date"
                    value={effectiveDate}
                    onChange={(e) => dispatch({ type: 'SET_DATE', expenseDate: e.target.value })}
                    disabled={fieldsDisabled}
                    data-testid="receipt-date-input"
                  />
                  {receipt.parsed_date == null && (
                    <Text fontSize="xs" color="gray.500" data-testid="receipt-date-hint">
                      No date found on the receipt — defaulted to today.
                    </Text>
                  )}
                </Stack>
                <Stack gap={1}>
                  <Text fontWeight="medium" fontSize="sm">
                    Category
                  </Text>
                  <NativeSelectRoot>
                    <NativeSelectField
                      value={effectiveCategoryId}
                      onChange={(e) =>
                        dispatch({ type: 'SET_CATEGORY', categoryId: e.target.value })
                      }
                      disabled={fieldsDisabled}
                      data-testid="receipt-category-select"
                    >
                      {categories.map((cat) => (
                        <option key={cat.id} value={cat.id}>
                          {cat.icon ? `${cat.icon} ` : ''}
                          {cat.name}
                        </option>
                      ))}
                    </NativeSelectField>
                  </NativeSelectRoot>
                </Stack>
              </Stack>
            )}

            {state.phase === 'done' && (
              <Stack align="center" gap={4} py={8} data-testid="receipt-done">
                <Text fontWeight="medium" color="green.600">
                  Receipt added successfully!
                </Text>
              </Stack>
            )}
          </DialogBody>

          <DialogFooter>
            {(state.phase === 'idle' || state.phase === 'uploading') && (
              <Button variant="ghost" onClick={handleClose} disabled={state.phase === 'uploading'}>
                Cancel
              </Button>
            )}
            {state.phase === 'preview' && (
              <>
                <Button
                  variant="ghost"
                  onClick={() => dispatch({ type: 'RESET' })}
                  data-testid="receipt-back-btn"
                >
                  Back
                </Button>
                <Button
                  colorPalette="brand"
                  onClick={handleUpload}
                  data-testid="receipt-upload-btn"
                >
                  Upload
                </Button>
              </>
            )}
            {state.phase === 'reviewing' && (
              <>
                <Button variant="ghost" onClick={handleClose}>
                  Cancel
                </Button>
                <Button
                  colorPalette="brand"
                  onClick={() => confirmMutation.mutate()}
                  loading={confirmMutation.isPending}
                  data-testid="receipt-confirm-btn"
                >
                  Confirm
                </Button>
              </>
            )}
            {state.phase === 'done' && (
              <Button colorPalette="brand" onClick={handleClose} data-testid="receipt-close-btn">
                Close
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}
