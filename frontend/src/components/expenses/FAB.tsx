import { useState } from 'react'
import { Box } from '@chakra-ui/react'
import CreateExpenseDialog from './CreateExpenseDialog'

interface FABProps {
  familyId: string
}

function PlusIcon() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function FAB({ familyId }: FABProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Box
        as="button"
        position="fixed"
        bottom="80px"
        right="16px"
        zIndex="overlay"
        w="56px"
        h="56px"
        minW="48px"
        minH="48px"
        borderRadius="full"
        bg="brand.500"
        color="white"
        display="flex"
        alignItems="center"
        justifyContent="center"
        boxShadow="lg"
        cursor="pointer"
        transition="background-color 0.15s, box-shadow 0.15s, transform 0.1s"
        _hover={{ bg: 'brand.600', boxShadow: 'xl' }}
        _active={{ bg: 'brand.700', transform: 'scale(0.95)' }}
        _focusVisible={{
          outline: '2px solid',
          outlineColor: 'brand.500',
          outlineOffset: '2px',
        }}
        onClick={() => setOpen(true)}
        aria-label="Add expense"
        data-testid="fab-add-expense"
      >
        <PlusIcon />
      </Box>

      <CreateExpenseDialog open={open} onOpenChange={setOpen} familyId={familyId} />
    </>
  )
}

export default FAB
