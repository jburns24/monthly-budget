import { useState } from 'react'
import { Box, Button, Container, Flex, Heading, Spinner, Text, chakra } from '@chakra-ui/react'
import { Link as RouterLink } from 'react-router-dom'
import { useFamilyContext } from '@/contexts/FamilyContext'
import { useAssets } from '@/hooks/useAssets'
import { ASSET_TYPE_ICONS, ASSET_TYPE_LABELS, type AssetListItem } from '@/types/asset'
import { formatDateLabel, formatMoney } from '@/utils/assets'
import AssetFormDialog from '@/components/assets/AssetFormDialog'
import { PlusIcon } from '@/components/assets/icons'

const CardLink = chakra(RouterLink)

interface StatProps {
  label: string
  value: string
  color?: string
  testId: string
}

function Stat({ label, value, color = 'ink', testId }: StatProps) {
  return (
    <Box minW={0}>
      <Text fontSize="xs" color="ink.muted">
        {label}
      </Text>
      <Text
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

function placeLine(asset: AssetListItem): string {
  const place = [asset.city, asset.state].filter(Boolean).join(', ')
  return [place, ASSET_TYPE_LABELS[asset.asset_type]].filter(Boolean).join(' · ')
}

function AssetCard({ asset }: { asset: AssetListItem }) {
  const { summary } = asset
  const money = (cents: number | undefined) => (cents === undefined ? '—' : formatMoney(cents))
  const hasLoan = (summary?.loan_balance_cents ?? 0) > 0
  const equityColor = summary && summary.equity_cents < 0 ? 'overspend' : 'income'

  return (
    <CardLink
      to={`/assets/${asset.id}`}
      display="block"
      textDecoration="none"
      borderRadius="card"
      _hover={{ textDecoration: 'none' }}
    >
      <Box
        p={4}
        bg="surface.1"
        borderRadius="card"
        borderWidth="1px"
        borderColor="hairline"
        transition="background-color 0.15s"
        _hover={{ bg: 'surface.2' }}
        data-testid={`asset-card-${asset.id}`}
      >
        <Flex align="center" gap={3} mb={4}>
          <Flex
            align="center"
            justify="center"
            w="40px"
            h="40px"
            flexShrink={0}
            borderRadius="10px"
            bg="surface.2"
            borderWidth="1px"
            borderColor="hairline"
            fontSize="xl"
            aria-hidden="true"
          >
            {ASSET_TYPE_ICONS[asset.asset_type]}
          </Flex>
          <Box flex={1} minW={0}>
            <Text fontWeight="500" color="ink" truncate>
              {asset.name}
            </Text>
            <Text fontSize="xs" color="ink.muted" truncate>
              {placeLine(asset)}
            </Text>
          </Box>
          {asset.is_sold && (
            <Text
              fontSize="xs"
              fontWeight="500"
              color="ink.muted"
              px={2}
              py={1}
              borderRadius="pill"
              borderWidth="1px"
              borderColor="hairline"
              whiteSpace="nowrap"
              flexShrink={0}
            >
              Sold{asset.sold_date ? ` ${formatDateLabel(asset.sold_date)}` : ''}
            </Text>
          )}
        </Flex>
        <Box
          display="grid"
          gridTemplateColumns={{
            base: 'repeat(2, minmax(0, 1fr))',
            md: 'repeat(4, minmax(0, 1fr))',
          }}
          gap={3}
        >
          <Stat
            label={asset.is_sold ? 'Sale price' : 'Value'}
            value={money(summary?.market_value_cents)}
            testId={`asset-value-${asset.id}`}
          />
          {hasLoan && (
            <Stat
              label="Loan"
              value={money(summary?.loan_balance_cents)}
              testId={`asset-loan-${asset.id}`}
            />
          )}
          <Stat
            label="Equity"
            value={money(summary?.equity_cents)}
            color={equityColor}
            testId={`asset-equity-${asset.id}`}
          />
          <Stat
            label="Cash in"
            value={money(summary?.cash_in_cents)}
            testId={`asset-cash-in-${asset.id}`}
          />
        </Box>
      </Box>
    </CardLink>
  )
}

function AssetsPage() {
  const { familyId, role } = useFamilyContext()
  const [createOpen, setCreateOpen] = useState(false)
  const { data: assets, isLoading, isError } = useAssets(familyId)

  const active = assets?.filter((a) => !a.is_sold) ?? []
  const sold = assets?.filter((a) => a.is_sold) ?? []

  return (
    <Container
      maxW="1199px"
      px={{ base: 4, md: 8 }}
      pt={{ base: 4, md: 16 }}
      pb={{ base: '120px', md: 16 }}
    >
      <Flex align="center" justify="space-between" gap={3} mb={{ base: 4, md: 12 }}>
        <Box minW={0}>
          <Text
            display={{ base: 'none', md: 'block' }}
            color="ink.muted"
            fontSize="13px"
            fontWeight="500"
            textTransform="uppercase"
            letterSpacing="0.08em"
            mb={3}
          >
            What you own, and what it&apos;s worth
          </Text>
          <Heading
            as="h1"
            fontFamily="heading"
            fontSize={{ base: '28px', md: '85px' }}
            fontWeight="500"
            lineHeight="0.95"
            letterSpacing={{ base: '-1px', md: '-4.25px' }}
            color="ink"
          >
            Assets
          </Heading>
        </Box>
        {familyId && role === 'admin' && (
          <Button
            colorPalette="brand"
            borderRadius="pill"
            minH="44px"
            minW="44px"
            px={{ base: 0, md: 5 }}
            flexShrink={0}
            onClick={() => setCreateOpen(true)}
            aria-label="Add asset"
            data-testid="add-asset-btn"
          >
            <Box display={{ base: 'inline-flex', md: 'none' }}>
              <PlusIcon />
            </Box>
            <Box as="span" display={{ base: 'none', md: 'inline' }}>
              Add Asset
            </Box>
          </Button>
        )}
      </Flex>

      {!familyId && (
        <Box py={12} textAlign="center">
          <Text color="ink.muted">Create or join a family to track assets.</Text>
        </Box>
      )}

      {familyId && isLoading && (
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading assets" />
        </Flex>
      )}

      {familyId && isError && (
        <Box py={8} textAlign="center">
          <Text color="spend">Failed to load assets. Please refresh the page.</Text>
        </Box>
      )}

      {assets && assets.length === 0 && (
        <Box py={12} textAlign="center" data-testid="assets-empty">
          <Text color="ink.muted">
            No assets yet.{' '}
            {role === 'admin'
              ? 'Add your home or a car to see its value, equity and what you have put in.'
              : 'An admin can add your home or a car to track its value and equity.'}
          </Text>
        </Box>
      )}

      {active.length > 0 && (
        <Flex direction="column" gap={3} maxW={{ md: '720px' }} data-testid="assets-list">
          {active.map((asset) => (
            <AssetCard key={asset.id} asset={asset} />
          ))}
        </Flex>
      )}

      {sold.length > 0 && (
        <Box mt={8} maxW={{ md: '720px' }}>
          <Heading
            as="h2"
            fontSize="13px"
            fontWeight="500"
            textTransform="uppercase"
            letterSpacing="0.08em"
            color="ink.muted"
            mb={3}
          >
            Sold
          </Heading>
          <Flex direction="column" gap={3} data-testid="assets-sold-list">
            {sold.map((asset) => (
              <AssetCard key={asset.id} asset={asset} />
            ))}
          </Flex>
        </Box>
      )}

      {familyId && createOpen && (
        <AssetFormDialog familyId={familyId} onClose={() => setCreateOpen(false)} />
      )}
    </Container>
  )
}

export default AssetsPage
