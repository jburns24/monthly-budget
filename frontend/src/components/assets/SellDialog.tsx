import { useState } from 'react'
import { Input, SimpleGrid, Text } from '@chakra-ui/react'
import { sellAsset } from '@/api/assets'
import { useAssetMutation } from '@/hooks/useAssets'
import type { AssetDetail } from '@/types/asset'
import { formatDateLabel, parseDollarsToCents, todayString } from '@/utils/assets'
import FormDialog from './FormDialog'
import FormField from './FormField'

interface SellDialogProps {
  familyId: string
  asset: AssetDetail
  onClose: () => void
}

function SellDialog({ familyId, asset, onClose }: SellDialogProps) {
  const [soldDate, setSoldDate] = useState(todayString)
  const [price, setPrice] = useState('')
  const [costs, setCosts] = useState('')
  const priceCents = parseDollarsToCents(price)
  const costsCents = costs.trim() ? parseDollarsToCents(costs) : 0
  const today = todayString()
  const dateValid = soldDate >= asset.purchase_date && soldDate <= today

  const mutation = useAssetMutation(
    familyId,
    () =>
      sellAsset(familyId, asset.id, {
        sold_date: soldDate,
        sale_price_cents: priceCents!,
        selling_costs_cents: costsCents!,
      }),
    { success: 'Marked as sold', onSuccess: onClose }
  )

  return (
    <FormDialog
      title={`Mark ${asset.name} as sold`}
      onClose={onClose}
      onSubmit={() => mutation.mutate()}
      submitLabel="Mark as sold"
      submitTestId="sell-submit-btn"
      isValid={soldDate.length > 0 && dateValid && priceCents !== null && costsCents !== null}
      isPending={mutation.isPending}
    >
      <Text fontSize="xs" color="ink.muted">
        Numbers freeze as of the sale date. You can undo this later.
      </Text>
      <FormField
        label="Sale date"
        required
        hint={
          soldDate.length > 0 && !dateValid
            ? `Pick a date between the purchase (${formatDateLabel(asset.purchase_date)}) and today.`
            : undefined
        }
      >
        <Input
          type="date"
          min={asset.purchase_date}
          max={today}
          value={soldDate}
          onChange={(e) => setSoldDate(e.target.value)}
          disabled={mutation.isPending}
          data-testid="sell-date-input"
        />
      </FormField>
      <SimpleGrid columns={2} gap={3}>
        <FormField label="Sale price" required>
          <Input
            placeholder="0.00"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={mutation.isPending}
            data-testid="sell-price-input"
          />
        </FormField>
        <FormField label="Selling costs" hint="Agent fees, closing costs you paid.">
          <Input
            placeholder="0.00"
            value={costs}
            onChange={(e) => setCosts(e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={mutation.isPending}
            data-testid="sell-costs-input"
          />
        </FormField>
      </SimpleGrid>
    </FormDialog>
  )
}

export default SellDialog
