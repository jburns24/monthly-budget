import { Box, Flex, Text } from '@chakra-ui/react'
import { Chart, useChart } from '@chakra-ui/charts'
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { AssetHistoryPoint } from '@/types/asset'
import { formatMoney, formatMonthLabel, toChartData, type ChartRow } from '@/utils/assets'

interface StoryChartProps {
  points: AssetHistoryPoint[]
  /** Without a loan, equity is the market value, so the loan and equity lines would only repeat it. */
  hasLoan: boolean
}

type SeriesKey = Exclude<keyof ChartRow, 'date'>

interface SeriesConfig {
  name: SeriesKey
  label: string
  color: string
  strokeDasharray?: string
}

const compactDollars = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
})

function seriesFor(hasLoan: boolean): SeriesConfig[] {
  const marketValue: SeriesConfig = {
    name: 'marketValue',
    label: 'Market value',
    color: 'accent.500',
  }
  const cashIn: SeriesConfig = {
    name: 'cashIn',
    label: 'Cash in',
    color: 'mutedLabel',
    strokeDasharray: '5 4',
  }
  if (!hasLoan) return [marketValue, cashIn]
  return [
    marketValue,
    { name: 'loanBalance', label: 'Loan balance', color: 'overspend' },
    { name: 'equity', label: 'Equity', color: 'income' },
    cashIn,
  ]
}

interface TooltipRowsProps extends Partial<
  Pick<TooltipContentProps, 'active' | 'payload' | 'label'>
> {
  series: SeriesConfig[]
  colorOf: (token: string) => string
}

// Chakra's Chart.Tooltip drops a value of exactly 0 (a paid-off loan, zero equity), so rows are drawn here.
function TooltipRows({ active, payload, label, series, colorOf }: TooltipRowsProps) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as ChartRow
  return (
    <Box
      bg="surface.2"
      borderWidth="1px"
      borderColor="hairline"
      borderRadius="10px"
      px={3}
      py={2}
      boxShadow="0 8px 24px rgba(0,0,0,0.4)"
    >
      <Text fontSize="xs" color="ink.muted" mb={1}>
        {formatMonthLabel(String(label ?? row.date))}
      </Text>
      {series.map((s) => (
        <Flex key={s.name} align="center" justify="space-between" gap={4} fontSize="sm">
          <Flex align="center" gap={2}>
            <Box w="10px" h="3px" borderRadius="full" bg={colorOf(s.color)} />
            <Text color="ink.muted">{s.label}</Text>
          </Flex>
          <Text fontVariantNumeric="tabular-nums" fontWeight="500">
            {formatMoney(Math.round(row[s.name] * 100))}
          </Text>
        </Flex>
      ))}
    </Box>
  )
}

function StoryChart({ points, hasLoan }: StoryChartProps) {
  const data = toChartData(points)
  const series = seriesFor(hasLoan)
  const chart = useChart<ChartRow>({ data, series })
  const latest = data[data.length - 1]

  const summary = latest
    ? `Chart over time. Latest: ${series.map((s) => `${s.label} ${formatMoney(Math.round(latest[s.name] * 100))}`).join(', ')}.`
    : 'Chart over time.'

  return (
    <Box data-testid="story-chart">
      <Flex wrap="wrap" gap={4} mb={3} aria-hidden="true">
        {series.map((s) => (
          <Flex key={s.name} align="center" gap={2} fontSize="xs" color="ink.muted">
            <Box
              w="14px"
              h="0"
              borderTopWidth="2px"
              borderTopStyle={s.strokeDasharray ? 'dashed' : 'solid'}
              borderColor={chart.color(s.color)}
            />
            {s.label}
          </Flex>
        ))}
      </Flex>
      <Chart.Root h={{ base: '240px', md: '340px' }} chart={chart} role="img" aria-label={summary}>
        <LineChart data={chart.data} responsive margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={chart.color('hairline.soft')} vertical={false} />
          <XAxis
            dataKey={chart.key('date')}
            tickFormatter={formatMonthLabel}
            minTickGap={36}
            axisLine={false}
            tickLine={false}
            tickMargin={8}
            tick={{ fill: chart.color('ink.muted'), fontSize: 12 }}
            padding={{ left: 8, right: 16 }}
          />
          <YAxis
            width={56}
            axisLine={false}
            tickLine={false}
            tickMargin={4}
            tickFormatter={(v: number) => compactDollars.format(v)}
            tick={{ fill: chart.color('ink.muted'), fontSize: 12 }}
          />
          <Tooltip
            cursor={{ stroke: chart.color('hairline'), strokeWidth: 1 }}
            animationDuration={100}
            content={({ active, payload, label }) => (
              <TooltipRows
                active={active}
                payload={payload}
                label={label}
                series={series}
                colorOf={(token) => chart.color(token)}
              />
            )}
          />
          {series.map((s) => (
            <Line
              key={s.name}
              type="monotone"
              dataKey={chart.key(s.name)}
              stroke={chart.color(s.color)}
              strokeWidth={2}
              strokeDasharray={s.strokeDasharray}
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </Chart.Root>
    </Box>
  )
}

export default StoryChart
