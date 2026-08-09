import { createSystem, defaultConfig, defineConfig } from '@chakra-ui/react'

const config = defineConfig({
  theme: {
    tokens: {
      colors: {
        brand: {
          50: { value: '#202020' },
          100: { value: '#292929' },
          200: { value: '#3a3a3a' },
          300: { value: '#666666' },
          400: { value: '#d9d9d9' },
          500: { value: '#ffffff' },
          600: { value: '#eeeeee' },
          700: { value: '#d8d8d8' },
          800: { value: '#b7b7b7' },
          900: { value: '#999999' },
        },
        accent: {
          50: { value: '#071f31' },
          100: { value: '#0a2d46' },
          200: { value: '#0b4268' },
          300: { value: '#076ba9' },
          400: { value: '#0099ff' },
          500: { value: '#0099ff' },
          600: { value: '#33adff' },
          700: { value: '#66c2ff' },
          800: { value: '#99d6ff' },
          900: { value: '#ccebff' },
        },
        teal: {
          50: { value: '#191919' },
          100: { value: '#242424' },
          200: { value: '#333333' },
          300: { value: '#555555' },
          400: { value: '#777777' },
          500: { value: '#999999' },
          600: { value: '#b5b5b5' },
          700: { value: '#d0d0d0' },
          800: { value: '#e8e8e8' },
          900: { value: '#ffffff' },
        },
        canvas: { value: '#080808' },
        surface: {
          1: { value: '#171717' },
          2: { value: '#222222' },
          3: { value: '#2c2c2c' },
        },
        ink: {
          DEFAULT: { value: '#ffffff' },
          muted: { value: '#999999' },
        },
        hairline: {
          DEFAULT: { value: '#303030' },
          soft: { value: '#222222' },
        },
        gradient: {
          violet: { value: '#6f46d9' },
          magenta: { value: '#d44bd3' },
          orange: { value: '#f47a3b' },
          coral: { value: '#ef6a72' },
        },
      },
      fonts: {
        heading: {
          value:
            '"Arial Rounded MT Bold", "Helvetica Neue", Inter, ui-sans-serif, system-ui, sans-serif',
        },
        body: { value: 'Inter, "Helvetica Neue", ui-sans-serif, system-ui, sans-serif' },
      },
      radii: {
        card: { value: '20px' },
        spotlight: { value: '30px' },
        pill: { value: '100px' },
      },
    },
    semanticTokens: {
      colors: {
        bg: {
          value: '{colors.canvas}',
          panel: { value: '{colors.surface.1}' },
          muted: { value: '{colors.surface.1}' },
          subtle: { value: '{colors.surface.2}' },
          emphasized: { value: '{colors.surface.3}' },
          inverted: { value: '{colors.white}' },
        },
        fg: {
          value: '{colors.ink}',
          muted: { value: '{colors.ink.muted}' },
          subtle: { value: '{colors.ink.muted}' },
          inverted: { value: '{colors.canvas}' },
        },
        border: {
          value: '{colors.hairline}',
          muted: { value: '{colors.hairline.soft}' },
          subtle: { value: '{colors.hairline.soft}' },
        },
        brand: {
          solid: { value: '{colors.brand.500}' },
          contrast: { value: '{colors.canvas}' },
          fg: { value: '{colors.brand.500}' },
          muted: { value: '{colors.surface.1}' },
          subtle: { value: '{colors.surface.2}' },
          emphasized: { value: '{colors.surface.3}' },
          focusRing: { value: '{colors.accent.500}' },
        },
      },
    },
  },
  globalCss: {
    'html, body': {
      minHeight: '100%',
      bg: 'canvas',
      color: 'ink',
    },
    body: {
      margin: 0,
      fontFamily: 'body',
      fontFeatureSettings: '"cv01", "cv05", "cv09", "cv11", "ss03", "ss07", "dlig"',
      letterSpacing: '-0.15px',
      lineHeight: '1.3',
      WebkitFontSmoothing: 'antialiased',
    },
    '*::selection': {
      bg: 'accent.500',
      color: 'canvas',
    },
    'a, button, input, select, textarea': {
      _focusVisible: {
        outline: 'none',
        boxShadow: '0 0 0 1px rgba(0, 153, 255, 0.7), 0 0 0 4px rgba(0, 153, 255, 0.15)',
      },
    },
    '[data-scope="dialog"][data-part="backdrop"]': {
      bg: 'rgba(0, 0, 0, 0.72)',
      backdropFilter: 'blur(8px)',
    },
    '[data-scope="dialog"][data-part="content"]': {
      bg: 'surface.1',
      color: 'ink',
      borderWidth: '1px',
      borderColor: 'hairline',
      borderRadius: '20px',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 30px 80px rgba(0,0,0,0.5)',
      overflow: 'hidden',
    },
    '[data-scope="dialog"] input, [data-scope="dialog"] select, [data-scope="dialog"] textarea': {
      bg: 'surface.2',
      color: 'ink',
      borderColor: 'hairline',
      borderRadius: '10px',
      minHeight: '44px',
    },
    '.chakra-dialog__footer > button:first-of-type': {
      background: '#222222 !important',
      color: '#ffffff !important',
      borderRadius: '100px !important',
    },
  },
})

const system = createSystem(defaultConfig, config)

export default system
