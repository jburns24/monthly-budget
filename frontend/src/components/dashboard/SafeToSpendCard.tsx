import { useEffect, useState } from 'react'
import { Box, Flex, Text } from '@chakra-ui/react'
import { formatCents } from '@/utils/format'

const ARC_PATH = 'M18,116 A97,97 0 0 1 212,116'
const ARC_LENGTH = 251.3
const INCOME = '#34e39b'
const SPEND = '#a855f7'
const OVERSPEND = '#f43f5e'
const MUTED = '#8b8f96'
const SURFACE = '#111113'
const BORDER = '#1e1e22'

export interface SafeToSpendCardProps {
  totalIncomeCents: number
  totalSpentCents: number
}

export default function SafeToSpendCard({
  totalIncomeCents,
  totalSpentCents,
}: SafeToSpendCardProps) {
  const zeroIncome = totalIncomeCents === 0
  const overspend = !zeroIncome && totalSpentCents > totalIncomeCents
  const net = totalIncomeCents - totalSpentCents
  const pct = zeroIncome ? 0 : Math.min(1, totalSpentCents / totalIncomeCents)
  const fillPct = overspend ? 1 : pct
  const targetOffset = ARC_LENGTH * (1 - fillPct)

  const [dashOffset, setDashOffset] = useState(ARC_LENGTH)

  useEffect(() => {
    const id = requestAnimationFrame(() => {
      setDashOffset(targetOffset)
    })
    return () => cancelAnimationFrame(id)
  }, [targetOffset])

  const amountCents = zeroIncome ? 0 : Math.abs(net)
  const label = overspend ? 'Over income' : 'Safe to spend'
  const amountColor = overspend ? OVERSPEND : INCOME
  const fillColor = overspend ? OVERSPEND : SPEND

  return (
    <Box
      mb={{ base: 4, md: 8 }}
      px="18px"
      py="20px"
      borderRadius="26px"
      bg={SURFACE}
      borderWidth="1px"
      borderStyle="solid"
      borderColor={BORDER}
      data-testid="safe-to-spend-card"
    >
      <Box position="relative" w="230px" h="132px" mx="auto">
        <svg width="230" height="132" viewBox="0 0 230 132" aria-hidden="true">
          <path
            d={ARC_PATH}
            fill="none"
            stroke={INCOME}
            strokeOpacity={0.28}
            strokeWidth={14}
            strokeLinecap="round"
            data-testid="safe-to-spend-track"
          />
          <path
            d={ARC_PATH}
            fill="none"
            stroke={fillColor}
            strokeWidth={14}
            strokeLinecap="round"
            pathLength={ARC_LENGTH}
            strokeDasharray={ARC_LENGTH}
            strokeDashoffset={dashOffset}
            style={{ transition: 'stroke-dashoffset 600ms ease-out' }}
            data-testid="safe-to-spend-fill"
          />
        </svg>
        <Flex
          position="absolute"
          left="0"
          right="0"
          bottom="8px"
          direction="column"
          align="center"
          gap="2px"
        >
          <Text
            fontSize="12px"
            color={MUTED}
            letterSpacing="0.08em"
            fontWeight="500"
            lineHeight="1.2"
          >
            {label}
          </Text>
          <Text
            fontSize="38px"
            fontWeight="600"
            letterSpacing="-0.02em"
            color={amountColor}
            lineHeight="1"
            fontVariantNumeric="tabular-nums"
            data-testid="safe-to-spend-amount"
          >
            {formatCents(amountCents)}
          </Text>
        </Flex>
      </Box>

      <Box h="1px" bg={BORDER} mt={3} mb={3} />

      {zeroIncome ? (
        <Text fontSize="12px" color={MUTED} textAlign="center" lineHeight="1.4">
          Add income to see what&apos;s safe to spend
        </Text>
      ) : (
        <Flex>
          <Flex flex="1" direction="column" align="flex-start" gap="4px" pr={3}>
            <Flex align="center" gap="6px">
              <Box w="7px" h="7px" borderRadius="2px" bg={INCOME} aria-hidden="true" />
              <Text fontSize="12px" color={MUTED} fontWeight="500">
                Income
              </Text>
            </Flex>
            <Text
              fontSize="19px"
              fontWeight="600"
              color="white"
              fontVariantNumeric="tabular-nums"
              data-testid="safe-to-spend-income"
            >
              {formatCents(totalIncomeCents)}
            </Text>
          </Flex>
          <Box w="1px" bg={BORDER} alignSelf="stretch" />
          <Flex flex="1" direction="column" align="flex-start" gap="4px" pl={3}>
            <Flex align="center" gap="6px">
              <Box w="7px" h="7px" borderRadius="2px" bg={SPEND} aria-hidden="true" />
              <Text fontSize="12px" color={MUTED} fontWeight="500">
                Spent
              </Text>
            </Flex>
            <Text
              fontSize="19px"
              fontWeight="600"
              color="white"
              fontVariantNumeric="tabular-nums"
              data-testid="safe-to-spend-spent"
            >
              {formatCents(totalSpentCents)}
            </Text>
          </Flex>
        </Flex>
      )}
    </Box>
  )
}
