import { useState } from 'react'
import {
  Box,
  Flex,
  Input,
  NativeSelectField,
  NativeSelectRoot,
  SimpleGrid,
  Text,
} from '@chakra-ui/react'
import { createAsset, updateAsset } from '@/api/assets'
import { useAssetMutation } from '@/hooks/useAssets'
import {
  ASSET_TYPE_LABELS,
  type AssetCreate,
  type AssetDetail,
  type AssetType,
} from '@/types/asset'
import {
  centsToInput,
  parseDollarsToCents,
  percentToRate,
  rateToPercent,
  todayString,
} from '@/utils/assets'
import FormDialog from './FormDialog'
import FormField from './FormField'
import LoanFields from './LoanFields'
import { emptyLoanForm, loanFormToInput, type LoanFormState } from './loanForm'

interface AssetFormDialogProps {
  familyId: string
  /** Set to edit this asset; omit to add a new one. */
  asset?: AssetDetail
  onClose: () => void
  /** Called with the saved asset. */
  onSaved?: (asset: AssetDetail) => void
}

const DEFAULT_DEPRECIATION_PERCENT = '15'

function AssetFormDialog({ familyId, asset, onClose, onSaved }: AssetFormDialogProps) {
  const editing = asset !== undefined

  const [name, setName] = useState(asset?.name ?? '')
  const [assetType, setAssetType] = useState<AssetType>(asset?.asset_type ?? 'house')
  const [purchaseDate, setPurchaseDate] = useState(asset?.purchase_date ?? todayString)
  const [price, setPrice] = useState(asset ? centsToInput(asset.purchase_price_cents) : '')
  const [downPayment, setDownPayment] = useState(
    asset?.down_payment_cents ? centsToInput(asset.down_payment_cents) : ''
  )
  const [closingCosts, setClosingCosts] = useState(
    asset?.closing_costs_cents ? centsToInput(asset.closing_costs_cents) : ''
  )
  const [line1, setLine1] = useState(asset?.address_line1 ?? '')
  const [city, setCity] = useState(asset?.city ?? '')
  const [state, setState] = useState(asset?.state ?? '')
  const [zip, setZip] = useState(asset?.zip_code ?? '')
  const [depreciation, setDepreciation] = useState(
    asset?.annual_depreciation_rate == null
      ? DEFAULT_DEPRECIATION_PERCENT
      : rateToPercent(asset.annual_depreciation_rate)
  )
  const [withLoan, setWithLoan] = useState(false)
  const [loan, setLoan] = useState<LoanFormState>(() => emptyLoanForm(todayString()))

  const isHouse = assetType === 'house'
  const isVehicle = assetType === 'vehicle'

  const priceCents = parseDollarsToCents(price)
  const downCents = downPayment.trim() ? parseDollarsToCents(downPayment) : 0
  const closingCents = closingCosts.trim() ? parseDollarsToCents(closingCosts) : 0
  const depreciationRate = depreciation.trim() ? percentToRate(depreciation, 4) : null
  const loanInput = withLoan ? loanFormToInput(loan) : null

  const isValid =
    name.trim().length > 0 &&
    purchaseDate.length > 0 &&
    priceCents !== null &&
    downCents !== null &&
    closingCents !== null &&
    (!isHouse || (/^[A-Za-z]{2}$/.test(state.trim()) && /^\d{5}$/.test(zip.trim()))) &&
    (!isVehicle || !depreciation.trim() || (depreciationRate !== null && depreciationRate <= 1)) &&
    (!withLoan || loanInput !== null)

  function buildFields(): Omit<AssetCreate, 'loan'> {
    const fields: Omit<AssetCreate, 'loan'> = {
      name: name.trim(),
      asset_type: assetType,
      purchase_date: purchaseDate,
      purchase_price_cents: priceCents ?? 0,
      down_payment_cents: downCents ?? 0,
      closing_costs_cents: closingCents ?? 0,
    }
    // Fields that don't apply to the new type are cleared when an existing asset changes type.
    const typeChanged = editing && assetType !== asset.asset_type
    if (isHouse) {
      fields.address_line1 = line1.trim() || null
      fields.city = city.trim() || null
      fields.state = state.trim().toUpperCase()
      fields.zip_code = zip.trim()
    } else if (typeChanged) {
      fields.address_line1 = null
      fields.city = null
      fields.state = null
      fields.zip_code = null
    }
    if (isVehicle) {
      // Leaving the default alone stores nothing, so the server's default keeps applying.
      const untouchedDefault =
        depreciation === DEFAULT_DEPRECIATION_PERCENT && asset?.annual_depreciation_rate == null
      if (!untouchedDefault) fields.annual_depreciation_rate = depreciationRate
    } else if (typeChanged) {
      fields.annual_depreciation_rate = null
    }
    return fields
  }

  const mutation = useAssetMutation(
    familyId,
    () => {
      const fields = buildFields()
      if (asset) return updateAsset(familyId, asset.id, fields)
      return createAsset(familyId, { ...fields, loan: loanInput })
    },
    {
      success: editing ? 'Asset updated' : 'Asset added',
      onSuccess: (saved) => {
        onSaved?.(saved)
        onClose()
      },
    }
  )

  return (
    <FormDialog
      title={editing ? 'Edit asset' : 'Add asset'}
      onClose={onClose}
      onSubmit={() => mutation.mutate()}
      submitLabel={editing ? 'Save' : 'Add asset'}
      submitTestId="asset-submit-btn"
      isValid={isValid}
      isPending={mutation.isPending}
    >
      <FormField label="Name" required>
        <Input
          placeholder={isVehicle ? 'e.g. Family minivan' : 'e.g. Maple Street'}
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
          disabled={mutation.isPending}
          data-testid="asset-name-input"
        />
      </FormField>
      <FormField label="Type">
        <NativeSelectRoot disabled={mutation.isPending}>
          <NativeSelectField
            value={assetType}
            onChange={(e) => setAssetType(e.target.value as AssetType)}
            data-testid="asset-type-select"
          >
            {(Object.keys(ASSET_TYPE_LABELS) as AssetType[]).map((type) => (
              <option key={type} value={type}>
                {ASSET_TYPE_LABELS[type]}
              </option>
            ))}
          </NativeSelectField>
        </NativeSelectRoot>
      </FormField>

      {isHouse && (
        <>
          <FormField label="Street address">
            <Input
              value={line1}
              onChange={(e) => setLine1(e.target.value)}
              maxLength={200}
              autoComplete="off"
              disabled={mutation.isPending}
              data-testid="asset-address-input"
            />
          </FormField>
          <SimpleGrid columns={{ base: 2, sm: 3 }} gap={3}>
            <Box gridColumn={{ base: 'span 2', sm: 'auto' }}>
              <FormField label="City">
                <Input
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  maxLength={100}
                  autoComplete="off"
                  disabled={mutation.isPending}
                  data-testid="asset-city-input"
                />
              </FormField>
            </Box>
            <FormField label="State" required>
              <Input
                placeholder="NC"
                value={state}
                onChange={(e) => setState(e.target.value.toUpperCase())}
                maxLength={2}
                autoComplete="off"
                disabled={mutation.isPending}
                data-testid="asset-state-input"
              />
            </FormField>
            <FormField label="ZIP" required>
              <Input
                placeholder="27601"
                value={zip}
                onChange={(e) => setZip(e.target.value)}
                inputMode="numeric"
                maxLength={5}
                autoComplete="off"
                disabled={mutation.isPending}
                data-testid="asset-zip-input"
              />
            </FormField>
          </SimpleGrid>
          <Text fontSize="xs" color="ink.muted" mt={-2}>
            State and ZIP let us estimate the value from regional home prices.
          </Text>
        </>
      )}

      {isVehicle && (
        <FormField label="Yearly depreciation (%)" hint="Value drops by this much each year.">
          <Input
            value={depreciation}
            onChange={(e) => setDepreciation(e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={mutation.isPending}
            data-testid="asset-depreciation-input"
          />
        </FormField>
      )}

      <SimpleGrid columns={2} gap={3}>
        <FormField label="Purchase date" required>
          <Input
            type="date"
            value={purchaseDate}
            onChange={(e) => setPurchaseDate(e.target.value)}
            disabled={mutation.isPending}
            data-testid="asset-purchase-date-input"
          />
        </FormField>
        <FormField label="Purchase price" required>
          <Input
            placeholder="0.00"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={mutation.isPending}
            data-testid="asset-price-input"
          />
        </FormField>
      </SimpleGrid>
      <SimpleGrid columns={2} gap={3}>
        <FormField label="Down payment">
          <Input
            placeholder="0.00"
            value={downPayment}
            onChange={(e) => setDownPayment(e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={mutation.isPending}
            data-testid="asset-down-payment-input"
          />
        </FormField>
        <FormField label="Closing costs">
          <Input
            placeholder="0.00"
            value={closingCosts}
            onChange={(e) => setClosingCosts(e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={mutation.isPending}
            data-testid="asset-closing-costs-input"
          />
        </FormField>
      </SimpleGrid>
      <Text fontSize="xs" color="ink.muted" mt={-2}>
        Down payment is the cash you put in up front. Paid in full? Enter the full price.
      </Text>

      {!editing && (
        <>
          <Flex as="label" align="center" gap={2} minH="44px" cursor="pointer">
            <input
              type="checkbox"
              checked={withLoan}
              onChange={(e) => setWithLoan(e.target.checked)}
              disabled={mutation.isPending}
              style={{ width: 18, height: 18 }}
              data-testid="asset-with-loan-checkbox"
            />
            <Text fontWeight="medium" fontSize="sm">
              This has a loan
            </Text>
          </Flex>
          {withLoan && <LoanFields value={loan} onChange={setLoan} disabled={mutation.isPending} />}
        </>
      )}
    </FormDialog>
  )
}

export default AssetFormDialog
