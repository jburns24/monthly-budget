import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { getAsset, getAssetExpenses, getAssetHistory, getAssets } from '@/api/assets'
import { toaster } from '@/components/ui/toaster'

// Detail, history and linked-expense keys all start with ['asset', familyId, assetId],
// so invalidating ['asset', familyId] refreshes every view of every asset.
export const assetKeys = {
  list: (familyId: string | null) => ['assets', familyId] as const,
  detail: (familyId: string | null, assetId: string) => ['asset', familyId, assetId] as const,
  history: (familyId: string | null, assetId: string) =>
    ['asset', familyId, assetId, 'history'] as const,
  expenses: (familyId: string | null, assetId: string) =>
    ['asset', familyId, assetId, 'expenses'] as const,
}

/** Refresh asset numbers after an entry is linked to, moved off or unlinked from an asset. */
export function invalidateAssets(
  queryClient: QueryClient,
  familyId: string,
  /** An asset that was just deleted: its views stay as they are, since refetching them would 404. */
  exceptAssetId?: string
) {
  queryClient.invalidateQueries({ queryKey: ['assets', familyId] })
  queryClient.invalidateQueries({
    queryKey: ['asset', familyId],
    predicate: (query) => query.queryKey[2] !== exceptAssetId,
  })
}

export function useAssets(familyId: string | null, enabled = true) {
  return useQuery({
    queryKey: assetKeys.list(familyId),
    queryFn: () => getAssets(familyId!),
    enabled: familyId !== null && enabled,
  })
}

export function useAsset(familyId: string | null, assetId: string) {
  return useQuery({
    queryKey: assetKeys.detail(familyId, assetId),
    queryFn: () => getAsset(familyId!, assetId),
    enabled: familyId !== null,
  })
}

export function useAssetHistory(familyId: string | null, assetId: string) {
  return useQuery({
    queryKey: assetKeys.history(familyId, assetId),
    queryFn: () => getAssetHistory(familyId!, assetId),
    enabled: familyId !== null,
  })
}

export function useAssetExpenses(familyId: string | null, assetId: string) {
  return useQuery({
    queryKey: assetKeys.expenses(familyId, assetId),
    queryFn: () => getAssetExpenses(familyId!, assetId),
    enabled: familyId !== null,
  })
}

interface AssetMutationOptions<TResult> {
  /** Toast title on success. */
  success: string
  onSuccess?: (result: TResult) => void
  /** The asset this write deletes: its cached views are left alone, not refetched (they would 404). */
  deletesAssetId?: string
}

/** A write against an asset: refreshes every asset view and any entries linked to one, then toasts. */
export function useAssetMutation<TResult>(
  familyId: string,
  mutationFn: () => Promise<TResult>,
  { success, onSuccess, deletesAssetId }: AssetMutationOptions<TResult>
) {
  const queryClient = useQueryClient()
  return useMutation<TResult, Error, void>({
    mutationFn,
    onSuccess: (result) => {
      invalidateAssets(queryClient, familyId, deletesAssetId)
      // Deleting an asset unlinks its expenses and recurring entries.
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
      toaster.create({ title: success, type: 'success', duration: 4000 })
      onSuccess?.(result)
    },
    onError: (error: Error) => {
      toaster.create({
        title: 'Error',
        description: error.message,
        type: 'error',
        duration: 4000,
      })
    },
  })
}
