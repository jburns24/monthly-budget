import { useState } from 'react'
import { Input } from '@chakra-ui/react'
import { addCorrection } from '@/api/assets'
import { useAssetMutation } from '@/hooks/useAssets'
import { parseDollarsToCents, todayString } from '@/utils/assets'
import FormDialog from './FormDialog'
import FormField from './FormField'

interface CorrectionDialogProps {
  familyId: string
  assetId: string
  onClose: () => void
}

function CorrectionDialog({ familyId, assetId, onClose }: CorrectionDialogProps) {
  const [asOf, setAsOf] = useState(todayString)
  const [balance, setBalance] = useState('')
  const cents = parseDollarsToCents(balance)

  const mutation = useAssetMutation(
    familyId,
    () => addCorrection(familyId, assetId, { as_of_date: asOf, balance_cents: cents! }),
    { success: 'Balance correction added', onSuccess: onClose }
  )

  return (
    <FormDialog
      title="Add balance correction"
      onClose={onClose}
      onSubmit={() => mutation.mutate()}
      submitLabel="Save"
      submitTestId="correction-submit-btn"
      isValid={asOf.length > 0 && cents !== null}
      isPending={mutation.isPending}
    >
      <FormField label="As of" required>
        <Input
          type="date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          disabled={mutation.isPending}
          data-testid="correction-date-input"
        />
      </FormField>
      <FormField
        label="Balance owed"
        required
        hint="From your lender's statement. The schedule picks up from this balance."
      >
        <Input
          placeholder="0.00"
          value={balance}
          onChange={(e) => setBalance(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          disabled={mutation.isPending}
          data-testid="correction-balance-input"
        />
      </FormField>
    </FormDialog>
  )
}

export default CorrectionDialog
