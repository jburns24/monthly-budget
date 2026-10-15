import { useEffect, useRef } from 'react'
import { NativeSelectField, NativeSelectRoot, Stack } from '@chakra-ui/react'
import { useAssets } from '@/hooks/useAssets'
import { ASSET_ROLE_HINTS, ASSET_ROLE_LABELS, type AssetRole } from '@/types/asset'
import { defaultAssetRole } from '@/utils/assets'
import FormField from './FormField'
import { NO_ASSET_LINK, type AssetLink } from './assetLink'

const ROLES = Object.keys(ASSET_ROLE_LABELS) as AssetRole[]

interface AssetLinkFieldsProps {
  familyId: string
  value: AssetLink
  onChange: (next: AssetLink) => void
  /** Recurring entries default to loan_payment on an asset that has a loan. */
  recurring?: boolean
  /** Load the asset list only while the dialog is open. */
  enabled?: boolean
  disabled?: boolean
}

/**
 * Optional "Asset" and "Role" pickers for an expense or recurring entry. Offers active assets,
 * plus the one already linked. Renders nothing for a family with no assets to link.
 */
function AssetLinkFields({
  familyId,
  value,
  onChange,
  recurring = false,
  enabled = true,
  disabled,
}: AssetLinkFieldsProps) {
  const { data: assets = [] } = useAssets(familyId, enabled)
  const options = assets.filter((a) => !a.is_sold || a.id === value.assetId)
  // A role that came with the entry, or that the person picked, is never replaced by a default.
  const roleChosen = useRef(value.assetId !== '')
  const lastRecurring = useRef(recurring)

  // Turning Repeat on or off changes which role is the likely default, so follow it.
  useEffect(() => {
    if (lastRecurring.current === recurring) return
    lastRecurring.current = recurring
    const asset = options.find((a) => a.id === value.assetId)
    if (asset && !roleChosen.current) {
      onChange({ assetId: asset.id, role: defaultAssetRole(asset, recurring) })
    }
  }, [recurring, options, value.assetId, onChange])

  if (options.length === 0) return null

  function chooseAsset(assetId: string) {
    const asset = options.find((a) => a.id === assetId)
    roleChosen.current = false
    onChange(asset ? { assetId, role: defaultAssetRole(asset, recurring) } : NO_ASSET_LINK)
  }

  function chooseRole(role: AssetRole) {
    roleChosen.current = true
    onChange({ ...value, role })
  }

  return (
    <Stack gap={4}>
      <FormField label="Asset">
        <NativeSelectRoot disabled={disabled}>
          <NativeSelectField
            value={value.assetId}
            onChange={(e) => chooseAsset(e.target.value)}
            data-testid="asset-link-select"
          >
            <option value="">None</option>
            {options.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </NativeSelectField>
        </NativeSelectRoot>
      </FormField>
      {value.assetId && (
        <FormField label="Counts as" hint={ASSET_ROLE_HINTS[value.role]}>
          <NativeSelectRoot disabled={disabled}>
            <NativeSelectField
              value={value.role}
              onChange={(e) => chooseRole(e.target.value as AssetRole)}
              data-testid="asset-role-select"
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {ASSET_ROLE_LABELS[role]}
                </option>
              ))}
            </NativeSelectField>
          </NativeSelectRoot>
        </FormField>
      )}
    </Stack>
  )
}

export default AssetLinkFields
