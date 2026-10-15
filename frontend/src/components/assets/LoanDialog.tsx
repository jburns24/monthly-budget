import { useState } from 'react'
import { Text } from '@chakra-ui/react'
import { upsertLoan } from '@/api/assets'
import { useAssetMutation } from '@/hooks/useAssets'
import type { AssetLoan } from '@/types/asset'
import { todayString } from '@/utils/assets'
import FormDialog from './FormDialog'
import LoanFields from './LoanFields'
import { emptyLoanForm, loanFormToInput, loanToForm, type LoanFormState } from './loanForm'

interface LoanDialogProps {
  familyId: string
  assetId: string
  /** The existing loan to edit; omit to add one. */
  loan?: AssetLoan | null
  onClose: () => void
}

function LoanDialog({ familyId, assetId, loan, onClose }: LoanDialogProps) {
  const [form, setForm] = useState<LoanFormState>(() =>
    loan ? loanToForm(loan) : emptyLoanForm(todayString())
  )
  const input = loanFormToInput(form)

  const mutation = useAssetMutation(familyId, () => upsertLoan(familyId, assetId, input!), {
    success: loan ? 'Loan updated' : 'Loan added',
    onSuccess: onClose,
  })

  return (
    <FormDialog
      title={loan ? 'Edit loan' : 'Add loan'}
      onClose={onClose}
      onSubmit={() => mutation.mutate()}
      submitLabel="Save"
      submitTestId="loan-submit-btn"
      isValid={input !== null}
      isPending={mutation.isPending}
    >
      {loan && (
        <Text fontSize="xs" color="ink.muted">
          Refinanced? Enter the new terms, then add a balance correction for the day it started.
        </Text>
      )}
      <LoanFields value={form} onChange={setForm} disabled={mutation.isPending} />
    </FormDialog>
  )
}

export default LoanDialog
