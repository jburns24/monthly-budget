import {
  Box,
  Flex,
  Input,
  NativeSelectField,
  NativeSelectRoot,
  Stack,
  Text,
} from '@chakra-ui/react'
import { FREQUENCY_LABELS, type Frequency } from '../../types/recurring'

interface RepeatFieldsProps {
  repeat: boolean
  onRepeatChange: (repeat: boolean) => void
  frequency: Frequency
  onFrequencyChange: (frequency: Frequency) => void
  endDate: string
  onEndDateChange: (endDate: string) => void
  /** Earliest allowed end date. */
  minEndDate?: string
  disabled?: boolean
  /** Checked but not changeable (e.g. the entry already belongs to a recurring rule). */
  locked?: boolean
  lockedHint?: string
}

/** "Repeat" checkbox that reveals the recurring-entry fields when checked. */
function RepeatFields({
  repeat,
  onRepeatChange,
  frequency,
  onFrequencyChange,
  endDate,
  onEndDateChange,
  minEndDate,
  disabled,
  locked,
  lockedHint,
}: RepeatFieldsProps) {
  const checked = repeat || !!locked
  return (
    <Stack gap={3}>
      <Box>
        <Flex as="label" align="center" gap={2} minH="44px" cursor="pointer">
          <input
            type="checkbox"
            checked={checked}
            disabled={disabled || locked}
            onChange={(e) => onRepeatChange(e.target.checked)}
            style={{ width: 18, height: 18 }}
            data-testid="repeat-checkbox"
          />
          <Text fontWeight="medium" fontSize="sm">
            Repeat
          </Text>
        </Flex>
        {locked && lockedHint && (
          <Text fontSize="xs" color="ink.muted" data-testid="repeat-locked-hint">
            {lockedHint}
          </Text>
        )}
      </Box>
      {repeat && !locked && (
        <Flex gap={3} direction={{ base: 'column', sm: 'row' }} data-testid="repeat-fields">
          <Stack gap={1} flex={1}>
            <Text fontWeight="medium" fontSize="sm">
              Repeats
            </Text>
            <NativeSelectRoot disabled={disabled}>
              <NativeSelectField
                value={frequency}
                onChange={(e) => onFrequencyChange(e.target.value as Frequency)}
                data-testid="repeat-frequency-select"
              >
                {(Object.keys(FREQUENCY_LABELS) as Frequency[]).map((f) => (
                  <option key={f} value={f}>
                    {FREQUENCY_LABELS[f]}
                  </option>
                ))}
              </NativeSelectField>
            </NativeSelectRoot>
          </Stack>
          <Stack gap={1} flex={1}>
            <Text fontWeight="medium" fontSize="sm">
              Ends (optional)
            </Text>
            <Input
              type="date"
              value={endDate}
              min={minEndDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              disabled={disabled}
              data-testid="repeat-end-input"
            />
          </Stack>
        </Flex>
      )}
    </Stack>
  )
}

export default RepeatFields
