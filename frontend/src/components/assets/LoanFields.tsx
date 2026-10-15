import { Input, NativeSelectField, NativeSelectRoot, SimpleGrid } from '@chakra-ui/react'
import FormField from './FormField'
import type { LoanFormState, TermUnit } from './loanForm'

interface LoanFieldsProps {
  value: LoanFormState
  onChange: (next: LoanFormState) => void
  disabled?: boolean
}

/** The loan terms, shared by the new-asset form and the edit-loan dialog. */
function LoanFields({ value, onChange, disabled }: LoanFieldsProps) {
  const set = <K extends keyof LoanFormState>(key: K, next: LoanFormState[K]) =>
    onChange({ ...value, [key]: next })

  return (
    <>
      <FormField label="Loan amount" required>
        <Input
          placeholder="0.00"
          value={value.amount}
          onChange={(e) => set('amount', e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          disabled={disabled}
          data-testid="loan-amount-input"
        />
      </FormField>
      <SimpleGrid columns={2} gap={3}>
        <FormField label="Interest rate (%)" required>
          <Input
            placeholder="6.25"
            value={value.ratePct}
            onChange={(e) => set('ratePct', e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={disabled}
            data-testid="loan-rate-input"
          />
        </FormField>
        <FormField label="Term" required group>
          <SimpleGrid columns={2} gap={2}>
            <Input
              value={value.term}
              onChange={(e) => set('term', e.target.value)}
              inputMode="numeric"
              autoComplete="off"
              disabled={disabled}
              aria-label="Loan term length"
              data-testid="loan-term-input"
            />
            <NativeSelectRoot disabled={disabled}>
              <NativeSelectField
                value={value.termUnit}
                onChange={(e) => set('termUnit', e.target.value as TermUnit)}
                aria-label="Loan term unit"
                data-testid="loan-term-unit-select"
              >
                <option value="years">years</option>
                <option value="months">months</option>
              </NativeSelectField>
            </NativeSelectRoot>
          </SimpleGrid>
        </FormField>
      </SimpleGrid>
      <FormField label="First payment date" required>
        <Input
          type="date"
          value={value.firstPaymentDate}
          onChange={(e) => set('firstPaymentDate', e.target.value)}
          disabled={disabled}
          data-testid="loan-first-payment-input"
        />
      </FormField>
      <SimpleGrid columns={2} gap={3}>
        <FormField
          label="Monthly payment"
          hint="Principal and interest. Leave blank to calculate it."
        >
          <Input
            placeholder="Calculated"
            value={value.payment}
            onChange={(e) => set('payment', e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={disabled}
            data-testid="loan-payment-input"
          />
        </FormField>
        <FormField label="Escrow per month" hint="Taxes and insurance paid through the lender.">
          <Input
            placeholder="0.00"
            value={value.escrow}
            onChange={(e) => set('escrow', e.target.value)}
            inputMode="decimal"
            autoComplete="off"
            disabled={disabled}
            data-testid="loan-escrow-input"
          />
        </FormField>
      </SimpleGrid>
    </>
  )
}

export default LoanFields
