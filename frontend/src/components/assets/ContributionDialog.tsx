import { useState } from 'react'
import { Input, NativeSelectField, NativeSelectRoot } from '@chakra-ui/react'
import { addContribution, updateContribution } from '@/api/assets'
import { useAssetMutation } from '@/hooks/useAssets'
import {
  ASSET_ROLE_HINTS,
  ASSET_ROLE_LABELS,
  CONTRIBUTION_ROLES,
  type AssetContribution,
  type ContributionRole,
} from '@/types/asset'
import { centsToInput, parseDollarsToCents, todayString } from '@/utils/assets'
import FormDialog from './FormDialog'
import FormField from './FormField'

interface ContributionDialogProps {
  familyId: string
  assetId: string
  /** The contribution to edit; omit to add one. */
  contribution?: AssetContribution
  onClose: () => void
}

function ContributionDialog({ familyId, assetId, contribution, onClose }: ContributionDialogProps) {
  const [date, setDate] = useState(contribution?.contribution_date ?? todayString)
  const [amount, setAmount] = useState(contribution ? centsToInput(contribution.amount_cents) : '')
  const [role, setRole] = useState<ContributionRole>(contribution?.role ?? 'improvement')
  const [description, setDescription] = useState(contribution?.description ?? '')
  const cents = parseDollarsToCents(amount)

  const mutation = useAssetMutation(
    familyId,
    () => {
      const data = {
        contribution_date: date,
        amount_cents: cents!,
        role,
        description: description.trim(),
      }
      return contribution
        ? updateContribution(familyId, assetId, contribution.id, data)
        : addContribution(familyId, assetId, data)
    },
    { success: contribution ? 'Contribution updated' : 'Contribution added', onSuccess: onClose }
  )

  return (
    <FormDialog
      title={contribution ? 'Edit past spending' : 'Add past spending'}
      onClose={onClose}
      onSubmit={() => mutation.mutate()}
      submitLabel="Save"
      submitTestId="contribution-submit-btn"
      isValid={date.length > 0 && cents !== null && cents > 0}
      isPending={mutation.isPending}
    >
      <FormField
        label="Amount"
        required
        hint="Counts toward this asset's totals, not your monthly budget."
      >
        <Input
          placeholder="0.00"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          disabled={mutation.isPending}
          data-testid="contribution-amount-input"
        />
      </FormField>
      <FormField label="Date" required>
        <Input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          disabled={mutation.isPending}
          data-testid="contribution-date-input"
        />
      </FormField>
      <FormField label="Kind" hint={ASSET_ROLE_HINTS[role]}>
        <NativeSelectRoot disabled={mutation.isPending}>
          <NativeSelectField
            value={role}
            onChange={(e) => setRole(e.target.value as ContributionRole)}
            data-testid="contribution-role-select"
          >
            {CONTRIBUTION_ROLES.map((r) => (
              <option key={r} value={r}>
                {ASSET_ROLE_LABELS[r]}
              </option>
            ))}
          </NativeSelectField>
        </NativeSelectRoot>
      </FormField>
      <FormField label="Description">
        <Input
          placeholder="e.g. New roof"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={500}
          disabled={mutation.isPending}
          data-testid="contribution-description-input"
        />
      </FormField>
    </FormDialog>
  )
}

export default ContributionDialog
