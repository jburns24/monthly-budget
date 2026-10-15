import type { ReactNode } from 'react'
import { Box, Flex, Text } from '@chakra-ui/react'

interface ListRowProps {
  title: string
  meta?: string
  amount?: string
  /** Edit and delete buttons at the end of the row. */
  actions?: ReactNode
  testId: string
}

/** One entry in a detail-page list: title and meta on the left, amount and actions on the right. */
function ListRow({ title, meta, amount, actions, testId }: ListRowProps) {
  return (
    <Flex
      align="center"
      gap={3}
      py={2}
      borderTopWidth="1px"
      borderColor="hairline.soft"
      _first={{ borderTopWidth: 0 }}
      data-testid={testId}
    >
      <Box flex={1} minW={0}>
        <Text fontWeight="500" color="ink" truncate>
          {title}
        </Text>
        {meta && (
          <Text fontSize="xs" color="ink.muted" truncate>
            {meta}
          </Text>
        )}
      </Box>
      {amount && (
        <Text
          fontWeight="500"
          fontSize={{ base: 'sm', md: 'md' }}
          fontVariantNumeric="tabular-nums"
          whiteSpace="nowrap"
          flexShrink={0}
        >
          {amount}
        </Text>
      )}
      {actions}
    </Flex>
  )
}

export default ListRow
