import { lazy, Suspense, useState } from 'react'
import type { ReactNode } from 'react'
import { Box, Button, Container, Flex, Heading, Spinner, Text, chakra } from '@chakra-ui/react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'
import { useFamilyContext } from '@/contexts/FamilyContext'
import { useAsset, useAssetExpenses, useAssetHistory } from '@/hooks/useAssets'
import {
  ASSET_ROLE_LABELS,
  ASSET_TYPE_ICONS,
  ASSET_TYPE_LABELS,
  type AssetDetail,
  type AssetDetailSummary,
} from '@/types/asset'
import { formatDateLabel, formatMoney, rateToPercent, valuationDisclaimer } from '@/utils/assets'
import AssetDialogHost from '@/components/assets/AssetDialogHost'
import type { AssetDialogState } from '@/components/assets/assetDialogState'
import { ChevronLeftIcon, EditIcon, PlusIcon, TrashIcon } from '@/components/assets/icons'
import ListRow from '@/components/assets/ListRow'
import RowIconButton from '@/components/assets/RowIconButton'
import SectionCard from '@/components/assets/SectionCard'

// Recharts is the heaviest dependency here; keep it out of the main bundle.
const StoryChart = lazy(() => import('@/components/assets/StoryChart'))

const BackLink = chakra(RouterLink)

function termLabel(months: number): string {
  if (months % 12 === 0) {
    const years = months / 12
    return `${years} ${years === 1 ? 'year' : 'years'}`
  }
  return `${months} months`
}

function locationLine(asset: AssetDetail): string {
  const cityState = [asset.city, asset.state].filter(Boolean).join(', ')
  const place = [asset.address_line1, [cityState, asset.zip_code].filter(Boolean).join(' ')]
    .filter(Boolean)
    .join(', ')
  return place || ASSET_TYPE_LABELS[asset.asset_type]
}

interface HeadlineProps {
  label: string
  value: string
  color?: string
  testId: string
}

function Headline({ label, value, color = 'ink', testId }: HeadlineProps) {
  return (
    <Box p={4} bg="surface.1" borderRadius="card" borderWidth="1px" borderColor="hairline" minW={0}>
      <Text fontSize="xs" color="ink.muted" mb={1}>
        {label}
      </Text>
      <Text
        fontSize={{ base: 'xl', md: '2xl' }}
        fontWeight="500"
        fontVariantNumeric="tabular-nums"
        color={color}
        truncate
        data-testid={testId}
      >
        {value}
      </Text>
    </Box>
  )
}

function Line({ label, value, testId }: { label: string; value: ReactNode; testId?: string }) {
  return (
    <Flex justify="space-between" gap={3} py={1} fontSize="sm" data-testid={testId}>
      <Text color="ink.muted">{label}</Text>
      <Text fontWeight="500" fontVariantNumeric="tabular-nums" textAlign="right">
        {value}
      </Text>
    </Flex>
  )
}

function AdminButton({
  children,
  onClick,
  testId,
  danger,
}: {
  children: ReactNode
  onClick: () => void
  testId: string
  danger?: boolean
}) {
  return (
    <Button
      bg={danger ? 'transparent' : 'surface.2'}
      color={danger ? 'red.400' : 'ink'}
      borderRadius="pill"
      minH="44px"
      px={4}
      _hover={{ bg: 'surface.3' }}
      onClick={onClick}
      data-testid={testId}
    >
      {children}
    </Button>
  )
}

interface BreakdownRow {
  label: string
  cents: number
}

function BreakdownGroup({
  title,
  blurb,
  total,
  rows,
  color,
  testId,
}: {
  title: string
  blurb: string
  total: number
  rows: BreakdownRow[]
  color: string
  testId: string
}) {
  const shown = rows.filter((r) => r.cents !== 0)
  return (
    <Box data-testid={testId}>
      <Flex align="baseline" justify="space-between" gap={3}>
        <Flex align="center" gap={2}>
          <Box w="10px" h="10px" borderRadius="full" bg={color} aria-hidden="true" />
          <Text fontWeight="500">{title}</Text>
        </Flex>
        <Text fontWeight="500" fontVariantNumeric="tabular-nums">
          {formatMoney(total)}
        </Text>
      </Flex>
      <Text fontSize="xs" color="ink.muted" mb={1}>
        {blurb}
      </Text>
      {shown.map((row) => (
        <Line key={row.label} label={row.label} value={formatMoney(row.cents)} />
      ))}
    </Box>
  )
}

function Breakdown({ summary }: { summary: AssetDetailSummary }) {
  const building = summary.equity_building_cents
  const sunk = summary.sunk_cost_cents
  const total = building + sunk
  return (
    <SectionCard title="Where your cash went" testId="asset-breakdown">
      {total > 0 && (
        <Flex h="10px" borderRadius="full" overflow="hidden" mb={4} aria-hidden="true">
          <Box w={`${(building / total) * 100}%`} bg="income" />
          <Box w={`${(sunk / total) * 100}%`} bg="gradient.orange" />
        </Flex>
      )}
      <Flex direction="column" gap={5}>
        <BreakdownGroup
          title="Builds equity"
          blurb="Money that stays yours."
          total={building}
          color="income"
          testId="breakdown-equity-building"
          rows={[
            { label: 'Down payment', cents: summary.down_payment_cents },
            { label: 'Principal paid', cents: summary.principal_paid_cents },
            { label: 'Improvements', cents: summary.improvements_cents },
          ]}
        />
        <BreakdownGroup
          title="Sunk cost"
          blurb="The price of owning it."
          total={sunk}
          color="gradient.orange"
          testId="breakdown-sunk-cost"
          rows={[
            { label: 'Interest paid', cents: summary.interest_paid_cents },
            { label: 'Escrow (taxes and insurance)', cents: summary.escrow_paid_cents },
            { label: 'Closing costs', cents: summary.closing_costs_cents },
            { label: 'Maintenance', cents: summary.maintenance_cents },
            { label: 'Carrying costs', cents: summary.carrying_cost_cents },
          ]}
        />
      </Flex>
    </SectionCard>
  )
}

function AssetDetailPage() {
  const { assetId = '' } = useParams<{ assetId: string }>()
  const navigate = useNavigate()
  const { familyId, role } = useFamilyContext()
  const isAdmin = role === 'admin'
  const [dialog, setDialog] = useState<AssetDialogState | null>(null)

  const { data: asset, isLoading, isError } = useAsset(familyId, assetId)
  const history = useAssetHistory(familyId, assetId)
  const expenses = useAssetExpenses(familyId, assetId)

  const open = (next: AssetDialogState) => () => setDialog(next)

  if (isLoading || !familyId) {
    return (
      <Container maxW="1199px" px={{ base: 4, md: 8 }} pt={{ base: 4, md: 16 }}>
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading asset" />
        </Flex>
      </Container>
    )
  }

  if (isError || !asset) {
    return (
      <Container maxW="1199px" px={{ base: 4, md: 8 }} pt={{ base: 4, md: 16 }}>
        <Box py={12} textAlign="center" data-testid="asset-detail-error">
          <Text color="spend" mb={4}>
            We couldn&apos;t load this asset. It may have been deleted.
          </Text>
          <Button
            asChild
            bg="surface.2"
            color="ink"
            borderRadius="pill"
            minH="44px"
            _hover={{ bg: 'surface.3' }}
          >
            <RouterLink to="/assets">Back to assets</RouterLink>
          </Button>
        </Box>
      </Container>
    )
  }

  const { summary, loan } = asset
  const money = (cents: number | undefined) => (cents === undefined ? '—' : formatMoney(cents))
  const disclaimer = valuationDisclaimer(asset)
  const points = history.data?.points ?? []
  const valuations = [...asset.valuations].sort((a, b) => b.as_of_date.localeCompare(a.as_of_date))
  const corrections = [...asset.corrections].sort((a, b) =>
    b.as_of_date.localeCompare(a.as_of_date)
  )
  const contributions = [...asset.contributions].sort((a, b) =>
    b.contribution_date.localeCompare(a.contribution_date)
  )
  const linked = expenses.data ?? []
  const showsLoanPayments = linked.some((e) => e.asset_role === 'loan_payment')

  return (
    <Container
      maxW="1199px"
      px={{ base: 4, md: 8 }}
      pt={{ base: 4, md: 16 }}
      pb={{ base: '120px', md: 16 }}
    >
      <BackLink
        to="/assets"
        display="inline-flex"
        alignItems="center"
        gap={1}
        minH="44px"
        color="ink.muted"
        fontSize="sm"
        textDecoration="none"
        _hover={{ color: 'ink', textDecoration: 'none' }}
      >
        <ChevronLeftIcon />
        Assets
      </BackLink>

      <Flex align="flex-start" justify="space-between" gap={3} mb={{ base: 4, md: 8 }}>
        <Flex gap={3} minW={0} align="center">
          <Flex
            align="center"
            justify="center"
            w={{ base: '48px', md: '64px' }}
            h={{ base: '48px', md: '64px' }}
            flexShrink={0}
            borderRadius="14px"
            bg="surface.2"
            borderWidth="1px"
            borderColor="hairline"
            fontSize={{ base: '2xl', md: '3xl' }}
            aria-hidden="true"
          >
            {ASSET_TYPE_ICONS[asset.asset_type]}
          </Flex>
          <Box minW={0}>
            <Heading
              as="h1"
              fontFamily="heading"
              fontSize={{ base: '28px', md: '56px' }}
              fontWeight="500"
              lineHeight="1"
              letterSpacing={{ base: '-1px', md: '-2.8px' }}
              color="ink"
              overflowWrap="anywhere"
              data-testid="asset-detail-name"
            >
              {asset.name}
            </Heading>
            <Text fontSize="sm" color="ink.muted" mt={1} truncate>
              {locationLine(asset)} · Bought {formatDateLabel(asset.purchase_date)}
            </Text>
          </Box>
        </Flex>
        {isAdmin && (
          <RowIconButton
            label="Edit asset"
            onClick={open({ kind: 'edit-asset' })}
            testId="asset-edit-btn"
          >
            <EditIcon />
          </RowIconButton>
        )}
      </Flex>

      <Flex direction="column" gap={4} maxW={{ md: '860px' }}>
        <Box>
          <Box
            display="grid"
            gridTemplateColumns={{
              base: 'repeat(2, minmax(0, 1fr))',
              md: `repeat(${loan ? 4 : 3}, minmax(0, 1fr))`,
            }}
            gap={3}
          >
            <Headline
              label={asset.is_sold ? 'Sale price' : 'Value'}
              value={money(summary?.market_value_cents)}
              testId="asset-detail-value"
            />
            {loan && (
              <Headline
                label="Loan balance"
                value={money(summary?.loan_balance_cents)}
                testId="asset-detail-loan"
              />
            )}
            <Headline
              label="Equity"
              value={money(summary?.equity_cents)}
              color={summary && summary.equity_cents < 0 ? 'overspend' : 'income'}
              testId="asset-detail-equity"
            />
            <Headline
              label="Cash in"
              value={money(summary?.cash_in_cents)}
              testId="asset-detail-cash-in"
            />
          </Box>
          {asset.is_sold && summary?.net_gain_cents != null && (
            <Box mt={3}>
              <Headline
                label="Net gain after selling costs and loan"
                value={formatMoney(summary.net_gain_cents)}
                color={summary.net_gain_cents < 0 ? 'overspend' : 'income'}
                testId="asset-detail-net-gain"
              />
            </Box>
          )}
          {disclaimer && !asset.is_sold && (
            <Text fontSize="xs" color="ink.muted" mt={3} data-testid="asset-valuation-note">
              {disclaimer}
            </Text>
          )}
        </Box>

        <SectionCard title="Over time">
          {history.isLoading ? (
            <Flex justify="center" align="center" h={{ base: '240px', md: '340px' }}>
              <Spinner color="brand.500" aria-label="Loading history" />
            </Flex>
          ) : points.length >= 2 ? (
            <Suspense fallback={<Box h={{ base: '240px', md: '340px' }} />}>
              <StoryChart points={points} hasLoan={loan !== null} />
            </Suspense>
          ) : (
            <Text fontSize="sm" color="ink.muted" data-testid="asset-chart-empty">
              The chart fills in as months go by.
            </Text>
          )}
        </SectionCard>

        {summary && <Breakdown summary={summary} />}

        {(loan || isAdmin) && (
          <SectionCard
            title="Loan"
            testId="asset-loan-section"
            action={
              isAdmin && loan ? (
                <AdminButton onClick={open({ kind: 'loan' })} testId="loan-edit-btn">
                  Edit loan
                </AdminButton>
              ) : undefined
            }
          >
            {loan ? (
              <>
                <Line label="Original amount" value={formatMoney(loan.original_amount_cents)} />
                <Line
                  label="Interest rate"
                  value={`${rateToPercent(loan.annual_interest_rate)}%`}
                />
                <Line label="Term" value={termLabel(loan.term_months)} />
                <Line label="First payment" value={formatDateLabel(loan.first_payment_date)} />
                <Line
                  label={
                    loan.monthly_payment_cents == null
                      ? 'Monthly payment (calculated)'
                      : 'Monthly payment'
                  }
                  value={money(
                    loan.monthly_payment_cents ?? loan.computed_monthly_payment_cents ?? undefined
                  )}
                />
                {loan.escrow_monthly_cents > 0 && (
                  <Line label="Escrow per month" value={formatMoney(loan.escrow_monthly_cents)} />
                )}
                {loan.payoff_date_estimate && (
                  <Line
                    label="Estimated payoff"
                    value={formatDateLabel(loan.payoff_date_estimate)}
                  />
                )}

                <Flex align="center" justify="space-between" gap={3} mt={4} mb={1} minH="44px">
                  <Text fontWeight="500" fontSize="sm">
                    Balance corrections
                  </Text>
                  {isAdmin && (
                    <AdminButton onClick={open({ kind: 'correction' })} testId="correction-add-btn">
                      <PlusIcon size={16} /> Add
                    </AdminButton>
                  )}
                </Flex>
                {corrections.length === 0 ? (
                  <Text fontSize="xs" color="ink.muted">
                    None. If your lender&apos;s balance differs from the schedule, add a correction
                    and the schedule picks up from it.
                  </Text>
                ) : (
                  corrections.map((c) => (
                    <ListRow
                      key={c.id}
                      testId={`correction-row-${c.id}`}
                      title={formatDateLabel(c.as_of_date)}
                      amount={formatMoney(c.balance_cents)}
                      actions={
                        isAdmin && (
                          <RowIconButton
                            label={`Delete correction from ${formatDateLabel(c.as_of_date)}`}
                            onClick={open({ kind: 'delete-correction', id: c.id })}
                            testId={`correction-delete-${c.id}`}
                          >
                            <TrashIcon />
                          </RowIconButton>
                        )
                      }
                    />
                  ))
                )}
                {isAdmin && (
                  <Box mt={3}>
                    <AdminButton
                      danger
                      onClick={open({ kind: 'delete-loan' })}
                      testId="loan-delete-btn"
                    >
                      Remove loan
                    </AdminButton>
                  </Box>
                )}
              </>
            ) : (
              <Flex align="center" justify="space-between" gap={3}>
                <Text fontSize="sm" color="ink.muted">
                  No loan on this asset.
                </Text>
                <AdminButton onClick={open({ kind: 'loan' })} testId="loan-add-btn">
                  <PlusIcon size={16} /> Add loan
                </AdminButton>
              </Flex>
            )}
          </SectionCard>
        )}

        {(valuations.length > 0 || isAdmin) && (
          <SectionCard
            title="Your values"
            testId="asset-valuations-section"
            action={
              isAdmin ? (
                <AdminButton onClick={open({ kind: 'valuation' })} testId="valuation-add-btn">
                  <PlusIcon size={16} /> Add
                </AdminButton>
              ) : undefined
            }
          >
            {valuations.length === 0 ? (
              <Text fontSize="sm" color="ink.muted">
                Nothing entered, so the estimate above is used. Add an appraisal or quote to replace
                it.
              </Text>
            ) : (
              valuations.map((v) => (
                <ListRow
                  key={v.id}
                  testId={`valuation-row-${v.id}`}
                  title={formatDateLabel(v.as_of_date)}
                  meta={v.note ?? undefined}
                  amount={formatMoney(v.value_cents)}
                  actions={
                    isAdmin && (
                      <RowIconButton
                        label={`Delete value from ${formatDateLabel(v.as_of_date)}`}
                        onClick={open({ kind: 'delete-valuation', id: v.id })}
                        testId={`valuation-delete-${v.id}`}
                      >
                        <TrashIcon />
                      </RowIconButton>
                    )
                  }
                />
              ))
            )}
          </SectionCard>
        )}

        {(contributions.length > 0 || isAdmin) && (
          <SectionCard
            title="Past spending"
            testId="asset-contributions-section"
            action={
              isAdmin ? (
                <AdminButton onClick={open({ kind: 'contribution' })} testId="contribution-add-btn">
                  <PlusIcon size={16} /> Add
                </AdminButton>
              ) : undefined
            }
          >
            {contributions.length === 0 ? (
              <Text fontSize="sm" color="ink.muted">
                Money you put in before you started tracking, like a past renovation. It counts
                toward this asset&apos;s totals, never your budget.
              </Text>
            ) : (
              contributions.map((c) => (
                <ListRow
                  key={c.id}
                  testId={`contribution-row-${c.id}`}
                  title={c.description || ASSET_ROLE_LABELS[c.role]}
                  meta={`${formatDateLabel(c.contribution_date)} · ${ASSET_ROLE_LABELS[c.role]}`}
                  amount={formatMoney(c.amount_cents)}
                  actions={
                    isAdmin && (
                      <Flex gap={1}>
                        <RowIconButton
                          label={`Edit ${c.description || ASSET_ROLE_LABELS[c.role]}`}
                          onClick={open({ kind: 'contribution', contribution: c })}
                          testId={`contribution-edit-${c.id}`}
                        >
                          <EditIcon />
                        </RowIconButton>
                        <RowIconButton
                          label={`Delete ${c.description || ASSET_ROLE_LABELS[c.role]}`}
                          onClick={open({ kind: 'delete-contribution', id: c.id })}
                          testId={`contribution-delete-${c.id}`}
                        >
                          <TrashIcon />
                        </RowIconButton>
                      </Flex>
                    )
                  }
                />
              ))
            )}
          </SectionCard>
        )}

        <SectionCard title="Linked expenses" testId="asset-expenses-section">
          {expenses.isLoading ? (
            <Spinner size="sm" color="brand.500" aria-label="Loading linked expenses" />
          ) : linked.length === 0 ? (
            <Text fontSize="sm" color="ink.muted">
              Nothing linked yet. Pick this asset when you add an expense to count repairs,
              improvements and other costs here.
            </Text>
          ) : (
            <Box data-testid="asset-expenses-list">
              {linked.map((e) => (
                <ListRow
                  key={e.id}
                  testId={`asset-expense-row-${e.id}`}
                  title={e.description || e.category?.name || 'Expense'}
                  meta={`${formatDateLabel(e.expense_date)}${e.asset_role ? ` · ${ASSET_ROLE_LABELS[e.asset_role]}` : ''}`}
                  amount={formatMoney(e.amount_cents)}
                />
              ))}
            </Box>
          )}
          {showsLoanPayments && (
            <Text fontSize="xs" color="ink.muted" mt={3}>
              Loan payments stay in your budget. This page uses the loan schedule for principal,
              interest and escrow.
            </Text>
          )}
        </SectionCard>

        {asset.is_sold && (
          <SectionCard title="Sale" testId="asset-sold-info">
            <Line label="Sold" value={asset.sold_date ? formatDateLabel(asset.sold_date) : '—'} />
            <Line label="Sale price" value={money(asset.sale_price_cents ?? undefined)} />
            <Line label="Selling costs" value={money(asset.selling_costs_cents ?? undefined)} />
          </SectionCard>
        )}

        {isAdmin && (
          <SectionCard title="Manage" testId="asset-manage-section">
            <Flex wrap="wrap" gap={2}>
              {asset.is_sold ? (
                <AdminButton onClick={open({ kind: 'unsell' })} testId="unsell-btn">
                  Undo sale
                </AdminButton>
              ) : (
                <AdminButton onClick={open({ kind: 'sell' })} testId="sell-btn">
                  Mark as sold
                </AdminButton>
              )}
              <AdminButton
                danger
                onClick={open({ kind: 'delete-asset' })}
                testId="delete-asset-btn"
              >
                Delete asset
              </AdminButton>
            </Flex>
          </SectionCard>
        )}
      </Flex>

      <AssetDialogHost
        familyId={familyId}
        asset={asset}
        dialog={dialog}
        onClose={() => setDialog(null)}
        onDeleted={() => navigate('/assets', { replace: true })}
      />
    </Container>
  )
}

export default AssetDetailPage
