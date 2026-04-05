import {
  Toaster as ChakraToaster,
  Portal,
  Spinner,
  Stack,
  ToastCloseTrigger,
  ToastDescription,
  ToastIndicator,
  ToastRoot,
  ToastTitle,
  createToaster,
} from '@chakra-ui/react'

// eslint-disable-next-line react-refresh/only-export-components
export const toaster = createToaster({
  placement: 'bottom',
  pauseOnPageIdle: true,
})

export function Toaster() {
  return (
    <Portal>
      <ChakraToaster toaster={toaster} insetInline={{ mdDown: '4' }}>
        {(toast) => (
          <ToastRoot width="sm">
            {toast.type === 'loading' ? (
              <Spinner size="sm" color="blue.solid" flexShrink="0" />
            ) : (
              <ToastIndicator />
            )}
            <Stack gap="1" flex="1" maxWidth="100%">
              {toast.title && <ToastTitle>{toast.title}</ToastTitle>}
              {toast.description && <ToastDescription>{toast.description}</ToastDescription>}
            </Stack>
            {toast.meta?.closable && <ToastCloseTrigger />}
          </ToastRoot>
        )}
      </ChakraToaster>
    </Portal>
  )
}
