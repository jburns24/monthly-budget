import type { ReactNode } from 'react'
import { Button } from '@chakra-ui/react'

interface RowIconButtonProps {
  label: string
  onClick: () => void
  testId: string
  children: ReactNode
}

/** Round 44px icon button at the end of a list row. */
function RowIconButton({ label, onClick, testId, children }: RowIconButtonProps) {
  return (
    <Button
      bg="surface.2"
      color="ink"
      borderRadius="full"
      w="44px"
      h="44px"
      minW="44px"
      p={0}
      flexShrink={0}
      _hover={{ bg: 'surface.3' }}
      onClick={onClick}
      aria-label={label}
      data-testid={testId}
    >
      {children}
    </Button>
  )
}

export default RowIconButton
