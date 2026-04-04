import { createSystem, defaultConfig } from '@chakra-ui/react'

const system = createSystem(defaultConfig, {
  theme: {
    tokens: {
      colors: {
        brand: {
          50: { value: '#e6f0f7' },
          100: { value: '#b3d1e6' },
          200: { value: '#80b2d4' },
          300: { value: '#4d93c3' },
          400: { value: '#2674b1' },
          500: { value: '#002B5B' },
          600: { value: '#002550' },
          700: { value: '#001f44' },
          800: { value: '#001938' },
          900: { value: '#00132d' },
        },
        accent: {
          50: { value: '#e6f5ed' },
          100: { value: '#b3e0ca' },
          200: { value: '#80cba7' },
          300: { value: '#4db684' },
          400: { value: '#26a166' },
          500: { value: '#006D3E' },
          600: { value: '#006037' },
          700: { value: '#00532f' },
          800: { value: '#004627' },
          900: { value: '#00391f' },
        },
        teal: {
          50: { value: '#e8f2f6' },
          100: { value: '#b9d8e4' },
          200: { value: '#8abed2' },
          300: { value: '#5ba4c0' },
          400: { value: '#3a8aae' },
          500: { value: '#1A5F7A' },
          600: { value: '#17546c' },
          700: { value: '#13495e' },
          800: { value: '#103e50' },
          900: { value: '#0c3342' },
        },
      },
    },
  },
})

export default system
