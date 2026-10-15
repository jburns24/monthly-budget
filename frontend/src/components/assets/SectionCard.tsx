import type { ReactNode } from 'react'
import { Box, Flex, Heading } from '@chakra-ui/react'

interface SectionCardProps {
  title: string
  /** Control shown at the end of the header, e.g. an Add button. */
  action?: ReactNode
  testId?: string
  children: ReactNode
}

/** A titled card on the asset detail page. */
function SectionCard({ title, action, testId, children }: SectionCardProps) {
  return (
    <Box
      as="section"
      p={4}
      bg="surface.1"
      borderRadius="card"
      borderWidth="1px"
      borderColor="hairline"
      data-testid={testId}
    >
      <Flex align="center" justify="space-between" gap={3} mb={3} minH="44px">
        <Heading as="h2" fontSize="md" fontWeight="500" color="ink">
          {title}
        </Heading>
        {action}
      </Flex>
      {children}
    </Box>
  )
}

export default SectionCard
