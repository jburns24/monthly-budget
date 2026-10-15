import { useState } from 'react'
import { Input } from '@chakra-ui/react'
import { addValuation } from '@/api/assets'
import { useAssetMutation } from '@/hooks/useAssets'
import { parseDollarsToCents, todayString } from '@/utils/assets'
import FormDialog from './FormDialog'
import FormField from './FormField'

interface ValuationDialogProps {
  familyId: string
  assetId: string
  onClose: () => void
}

function ValuationDialog({ familyId, assetId, onClose }: ValuationDialogProps) {
  const [asOf, setAsOf] = useState(todayString)
  const [value, setValue] = useState('')
  const [note, setNote] = useState('')
  const cents = parseDollarsToCents(value)

  const mutation = useAssetMutation(
    familyId,
    () =>
      addValuation(familyId, assetId, {
        as_of_date: asOf,
        value_cents: cents!,
        note: note.trim() || null,
      }),
    { success: 'Value added', onSuccess: onClose }
  )

  return (
    <FormDialog
      title="Add a value"
      onClose={onClose}
      onSubmit={() => mutation.mutate()}
      submitLabel="Save"
      submitTestId="valuation-submit-btn"
      isValid={asOf.length > 0 && cents !== null}
      isPending={mutation.isPending}
    >
      <FormField label="As of" required>
        <Input
          type="date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          disabled={mutation.isPending}
          data-testid="valuation-date-input"
        />
      </FormField>
      <FormField
        label="Market value"
        required
        hint="Replaces the estimate from this date on, e.g. an appraisal or a trade-in quote."
      >
        <Input
          placeholder="0.00"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          disabled={mutation.isPending}
          data-testid="valuation-value-input"
        />
      </FormField>
      <FormField label="Note">
        <Input
          placeholder="e.g. Appraisal for refinance"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          disabled={mutation.isPending}
          data-testid="valuation-note-input"
        />
      </FormField>
    </FormDialog>
  )
}

export default ValuationDialog
