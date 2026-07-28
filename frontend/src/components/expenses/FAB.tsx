import { useState } from 'react'
import {
  Box,
  chakra,
  TooltipContent,
  TooltipPositioner,
  TooltipRoot,
  TooltipTrigger,
} from '@chakra-ui/react'

const ChakraButton = chakra('button')
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import CreateExpenseDialog from './CreateExpenseDialog'
import ReceiptCaptureDialog from './ReceiptCaptureDialog'

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

function CameraIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  )
}

function FAB({ familyId }: FABProps) {
  const [createOpen, setCreateOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)
  const isOnline = useOnlineStatus()

  const sharedFABStyles = {
    borderRadius: 'full' as const,
    color: 'white',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: 'lg',
    cursor: 'pointer',
    transition: 'background-color 0.15s, box-shadow 0.15s, transform 0.1s',
  } as const

  return (
    <>
      {/* Scan Receipt FAB — positioned above the main FAB */}
      <TooltipRoot openDelay={200} disabled={isOnline} positioning={{ placement: 'left' }}>
        <TooltipTrigger asChild>
          <Box
            as="span"
            position="fixed"
            bottom="148px"
            right="16px"
            zIndex="overlay"
            display="inline-block"
          >
            <ChakraButton
              w="48px"
              h="48px"
              minW="40px"
              minH="40px"
              {...sharedFABStyles}
              bg={isOnline ? 'brand.400' : 'gray.400'}
              _hover={isOnline ? { bg: 'brand.500', boxShadow: 'xl' } : undefined}
              _active={isOnline ? { bg: 'brand.600', transform: 'scale(0.95)' } : undefined}
              _focusVisible={{
                outline: '2px solid',
                outlineColor: 'brand.500',
                outlineOffset: '2px',
              }}
              disabled={!isOnline}
              style={{ pointerEvents: isOnline ? undefined : 'none' }}
              onClick={() => setScanOpen(true)}
              aria-label="Scan receipt"
              data-testid="fab-scan-receipt"
            >
              <CameraIcon />
            </ChakraButton>
          </Box>
        </TooltipTrigger>
        <TooltipPositioner>
          <TooltipContent>Receipt scanning requires a network connection.</TooltipContent>
        </TooltipPositioner>
      </TooltipRoot>

      {/* Add Expense FAB */}
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
        {...sharedFABStyles}
        bg="brand.500"
        _hover={{ bg: 'brand.600', boxShadow: 'xl' }}
        _active={{ bg: 'brand.700', transform: 'scale(0.95)' }}
        _focusVisible={{
          outline: '2px solid',
          outlineColor: 'brand.500',
          outlineOffset: '2px',
        }}
        onClick={() => setCreateOpen(true)}
        aria-label="Add expense"
        data-testid="fab-add-expense"
      >
        <PlusIcon />
      </Box>

      <CreateExpenseDialog open={createOpen} onOpenChange={setCreateOpen} familyId={familyId} />
      <ReceiptCaptureDialog open={scanOpen} onOpenChange={setScanOpen} familyId={familyId} />
    </>
  )
}

export default FAB
