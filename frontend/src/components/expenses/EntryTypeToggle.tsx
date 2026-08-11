import { HStack, RadioGroup } from '@chakra-ui/react'
import type { EntryType } from '../../types/expenses'

interface EntryTypeToggleProps {
  value: EntryType
  onChange: (value: EntryType) => void
  disabled?: boolean
}

function EntryTypeToggle({ value, onChange, disabled }: EntryTypeToggleProps) {
  return (
    <RadioGroup.Root
      value={value}
      onValueChange={(details) => {
        if (details.value === 'expense' || details.value === 'income') {
          onChange(details.value)
        }
      }}
      disabled={disabled}
      data-testid="entry-type-toggle"
      aria-label="Entry type"
    >
      <HStack gap={4}>
        <RadioGroup.Item value="expense">
          <RadioGroup.ItemHiddenInput />
          <RadioGroup.ItemIndicator />
          <RadioGroup.ItemText>Expense</RadioGroup.ItemText>
        </RadioGroup.Item>
        <RadioGroup.Item value="income">
          <RadioGroup.ItemHiddenInput />
          <RadioGroup.ItemIndicator />
          <RadioGroup.ItemText>Income</RadioGroup.ItemText>
        </RadioGroup.Item>
      </HStack>
    </RadioGroup.Root>
  )
}

export default EntryTypeToggle
