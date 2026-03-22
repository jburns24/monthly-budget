import { createSystem, defaultConfig } from '@chakra-ui/react'

const system = createSystem(defaultConfig, {
  theme: {
    tokens: {
      colors: {
        brand: {
          50: { value: '#e8f4fd' },
          100: { value: '#bee3f8' },
          200: { value: '#90cdf4' },
          300: { value: '#63b3ed' },
          400: { value: '#4299e1' },
          500: { value: '#3182ce' },
          600: { value: '#2b6cb0' },
          700: { value: '#2c5282' },
          800: { value: '#2a4365' },
          900: { value: '#1A365D' },
        },
      },
    },
  },
})

export default system
