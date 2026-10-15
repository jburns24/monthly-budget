import { apiClient } from './client'
import type {
  AssetContribution,
  AssetContributionCreate,
  AssetContributionUpdate,
  AssetCreate,
  AssetDetail,
  AssetExpensesResponse,
  AssetHistory,
  AssetListItem,
  AssetListResponse,
  AssetLoan,
  AssetLoanInput,
  AssetSell,
  AssetUpdate,
  AssetValuation,
  AssetValuationCreate,
  LoanCorrection,
  LoanCorrectionCreate,
} from '@/types/asset'
import type { Expense } from '@/types/expenses'

const base = (familyId: string) => `/api/families/${familyId}/assets`

/** The server's own message when it sent a plain-text `detail`, else the fixed fallback. */
async function failure(response: Response, fallback: string): Promise<Error> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return new Error(body.detail)
  } catch {
    // Not JSON; use the fallback.
  }
  return new Error(fallback)
}

async function send<T>(
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body: unknown,
  fallback: string
): Promise<T> {
  const response = await apiClient(path, {
    method,
    ...(body === undefined
      ? {}
      : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
  if (!response.ok) throw await failure(response, fallback)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function read<T>(path: string, fallback: string): Promise<T> {
  const response = await apiClient(path)
  if (!response.ok) throw await failure(response, fallback)
  return response.json() as Promise<T>
}

export async function getAssets(familyId: string): Promise<AssetListItem[]> {
  const data = await read<AssetListResponse>(base(familyId), 'Failed to fetch assets')
  return data.assets
}

export function getAsset(familyId: string, assetId: string): Promise<AssetDetail> {
  return read<AssetDetail>(`${base(familyId)}/${assetId}`, 'Failed to fetch asset')
}

export function getAssetHistory(familyId: string, assetId: string): Promise<AssetHistory> {
  return read<AssetHistory>(`${base(familyId)}/${assetId}/history`, 'Failed to fetch asset history')
}

export async function getAssetExpenses(familyId: string, assetId: string): Promise<Expense[]> {
  const data = await read<AssetExpensesResponse>(
    `${base(familyId)}/${assetId}/expenses`,
    'Failed to fetch linked expenses'
  )
  return data.expenses
}

export function createAsset(familyId: string, data: AssetCreate): Promise<AssetDetail> {
  return send<AssetDetail>(base(familyId), 'POST', data, 'Failed to create asset')
}

export function updateAsset(
  familyId: string,
  assetId: string,
  data: AssetUpdate
): Promise<AssetDetail> {
  return send<AssetDetail>(`${base(familyId)}/${assetId}`, 'PUT', data, 'Failed to update asset')
}

export function deleteAsset(familyId: string, assetId: string): Promise<void> {
  return send<void>(`${base(familyId)}/${assetId}`, 'DELETE', undefined, 'Failed to delete asset')
}

export function sellAsset(
  familyId: string,
  assetId: string,
  data: AssetSell
): Promise<AssetDetail> {
  return send<AssetDetail>(
    `${base(familyId)}/${assetId}/sell`,
    'POST',
    data,
    'Failed to mark as sold'
  )
}

export function unsellAsset(familyId: string, assetId: string): Promise<AssetDetail> {
  return send<AssetDetail>(
    `${base(familyId)}/${assetId}/sell`,
    'DELETE',
    undefined,
    'Failed to undo the sale'
  )
}

export function upsertLoan(
  familyId: string,
  assetId: string,
  data: AssetLoanInput
): Promise<AssetLoan> {
  return send<AssetLoan>(`${base(familyId)}/${assetId}/loan`, 'PUT', data, 'Failed to save loan')
}

export function deleteLoan(familyId: string, assetId: string): Promise<void> {
  return send<void>(
    `${base(familyId)}/${assetId}/loan`,
    'DELETE',
    undefined,
    'Failed to remove loan'
  )
}

export function addCorrection(
  familyId: string,
  assetId: string,
  data: LoanCorrectionCreate
): Promise<LoanCorrection> {
  return send<LoanCorrection>(
    `${base(familyId)}/${assetId}/loan/corrections`,
    'POST',
    data,
    'Failed to save balance correction'
  )
}

export function deleteCorrection(
  familyId: string,
  assetId: string,
  correctionId: string
): Promise<void> {
  return send<void>(
    `${base(familyId)}/${assetId}/loan/corrections/${correctionId}`,
    'DELETE',
    undefined,
    'Failed to delete balance correction'
  )
}

export function addValuation(
  familyId: string,
  assetId: string,
  data: AssetValuationCreate
): Promise<AssetValuation> {
  return send<AssetValuation>(
    `${base(familyId)}/${assetId}/valuations`,
    'POST',
    data,
    'Failed to save value'
  )
}

export function deleteValuation(
  familyId: string,
  assetId: string,
  valuationId: string
): Promise<void> {
  return send<void>(
    `${base(familyId)}/${assetId}/valuations/${valuationId}`,
    'DELETE',
    undefined,
    'Failed to delete value'
  )
}

export function addContribution(
  familyId: string,
  assetId: string,
  data: AssetContributionCreate
): Promise<AssetContribution> {
  return send<AssetContribution>(
    `${base(familyId)}/${assetId}/contributions`,
    'POST',
    data,
    'Failed to save contribution'
  )
}

export function updateContribution(
  familyId: string,
  assetId: string,
  contributionId: string,
  data: AssetContributionUpdate
): Promise<AssetContribution> {
  return send<AssetContribution>(
    `${base(familyId)}/${assetId}/contributions/${contributionId}`,
    'PUT',
    data,
    'Failed to update contribution'
  )
}

export function deleteContribution(
  familyId: string,
  assetId: string,
  contributionId: string
): Promise<void> {
  return send<void>(
    `${base(familyId)}/${assetId}/contributions/${contributionId}`,
    'DELETE',
    undefined,
    'Failed to delete contribution'
  )
}
