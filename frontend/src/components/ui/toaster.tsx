import { Toaster as ChakraToaster, createToaster } from '@chakra-ui/react'

// eslint-disable-next-line react-refresh/only-export-components
export const toaster = createToaster({
  placement: 'bottom',
  pauseOnPageIdle: true,
})

export function Toaster() {
  return <ChakraToaster toaster={toaster} />
}
