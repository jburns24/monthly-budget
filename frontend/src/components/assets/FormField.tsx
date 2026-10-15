import type { ReactNode } from 'react'
import { Field, Stack, Text } from '@chakra-ui/react'
import { useId } from 'react'

interface FormFieldProps {
  label: string
  required?: boolean
  hint?: string
  /**
   * The label names several controls (each with its own aria-label) rather than one: render it
   * as the label of a group instead of tying it to a single input.
   */
  group?: boolean
  children: ReactNode
}

/**
 * Label above a control, with an optional required star and a muted hint below it. The label,
 * the hint and the control are linked, so the control has an accessible name and description.
 */
function FormField({ label, required, hint, group, children }: FormFieldProps) {
  const labelId = useId()

  if (group) {
    return (
      <Stack gap={1} role="group" aria-labelledby={labelId}>
        <Text id={labelId} fontWeight="medium" fontSize="sm">
          {label}
          {required && (
            <>
              {' '}
              <Text as="span" color="red.500" aria-hidden="true">
                *
              </Text>
            </>
          )}
        </Text>
        {children}
        {hint && (
          <Text fontSize="xs" color="ink.muted">
            {hint}
          </Text>
        )}
      </Stack>
    )
  }

  return (
    <Field.Root required={required} gap={1} alignItems="stretch">
      <Field.Label fontWeight="medium" fontSize="sm">
        {label}
        <Field.RequiredIndicator />
      </Field.Label>
      {children}
      {hint && (
        <Field.HelperText fontSize="xs" color="ink.muted">
          {hint}
        </Field.HelperText>
      )}
    </Field.Root>
  )
}

export default FormField
