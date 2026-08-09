import { useState } from 'react'
import { Box, Button, Container, Flex, Heading, Text, VStack } from '@chakra-ui/react'
import { generateCodeVerifier, generateCodeChallenge, generateState } from '../utils/pkce'

const GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'

function LoginPage() {
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleSignIn = async (): Promise<void> => {
    setIsLoading(true)
    setError(null)

    try {
      const codeVerifier = generateCodeVerifier()
      const codeChallenge = await generateCodeChallenge(codeVerifier)
      const state = generateState()

      sessionStorage.setItem('pkce_code_verifier', codeVerifier)
      sessionStorage.setItem('oauth_state', state)

      const rawClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
      const clientId = typeof rawClientId === 'string' ? rawClientId : null
      if (!clientId) {
        throw new Error('Google Client ID is not configured. Please set VITE_GOOGLE_CLIENT_ID.')
      }

      const redirectUri = `${window.location.origin}/auth/callback`
      const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: 'openid email profile',
        code_challenge: codeChallenge,
        code_challenge_method: 'S256',
        state,
      })

      window.location.href = `${GOOGLE_AUTH_URL}?${params.toString()}`
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate sign in')
      setIsLoading(false)
    }
  }

  return (
    <Box
      minH="100svh"
      bg="canvas"
      display="flex"
      alignItems="center"
      justifyContent="center"
      py={{ base: 10, md: 16 }}
    >
      <Container maxW="1199px" px={{ base: 5, md: 8 }}>
        <Flex direction={{ base: 'column', md: 'row' }} align="stretch" gap={{ base: 10, md: 16 }}>
          <Box flex="1" display="flex" flexDirection="column" justifyContent="space-between">
            <Text color="ink.muted" fontSize="13px" fontWeight="500" letterSpacing="0.08em">
              MONTHLY.BUDGET
            </Text>
            <Box py={{ base: 10, md: 0 }}>
              <Heading
                as="h1"
                fontFamily="heading"
                fontSize={{ base: '58px', md: '85px', lg: '110px' }}
                lineHeight="0.85"
                letterSpacing={{ base: '-2.9px', md: '-4.25px', lg: '-5.5px' }}
                color="ink"
                fontWeight="500"
                maxW="720px"
              >
                Money,
                <br />
                made clear.
              </Heading>
              <Text color="ink.muted" fontSize="lg" mt={6} maxW="460px">
                A quieter place to plan, spend, and stay aligned with your household.
              </Text>
            </Box>
            <Text display={{ base: 'none', md: 'block' }} color="ink.muted" fontSize="xs">
              Plan together. Spend deliberately.
            </Text>
          </Box>

          <Box
            flex="0 1 440px"
            minH={{ base: 'auto', md: '560px' }}
            p={{ base: 6, md: 8 }}
            bg="surface.1"
            borderRadius="spotlight"
            borderWidth="1px"
            borderColor="hairline"
            boxShadow="inset 0 1px 0 rgba(255,255,255,0.08), 0 30px 80px rgba(0,0,0,0.4)"
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
          >
            <Box
              h="180px"
              borderRadius="card"
              background="radial-gradient(circle at 25% 20%, rgba(255,255,255,0.32), transparent 24%), radial-gradient(circle at 75% 80%, #ef6a72 0, transparent 42%), linear-gradient(135deg, #4d277e, #d44bd3 62%, #f47a3b)"
              boxShadow="inset 0 1px 0 rgba(255,255,255,0.18)"
              aria-hidden="true"
            />
            <VStack gap={6} align="stretch" mt={10}>
              <Box>
                <Heading
                  as="h2"
                  fontFamily="heading"
                  fontSize="32px"
                  fontWeight="500"
                  lineHeight="1.13"
                  letterSpacing="-1px"
                  color="ink"
                >
                  Monthly Budget
                </Heading>
                <Text fontSize="md" color="ink.muted" mt={2}>
                  Sign in to continue to your budget.
                </Text>
              </Box>

              {error !== null && (
                <Box
                  w="full"
                  p={3}
                  bg="rgba(239, 106, 114, 0.12)"
                  borderRadius="10px"
                  borderWidth="1px"
                  borderColor="rgba(239, 106, 114, 0.35)"
                  role="alert"
                >
                  <Text color="white" fontSize="sm">
                    {error}
                  </Text>
                </Box>
              )}
              <Button
                onClick={() => void handleSignIn()}
                disabled={isLoading}
                bg="white"
                color="canvas"
                size="lg"
                w="full"
                minH="48px"
                borderRadius="pill"
                fontWeight="500"
                gap={2}
                _hover={{ bg: 'brand.600', transform: 'translateY(-1px)' }}
                _active={{ transform: 'scale(0.98)' }}
              >
                <GoogleIcon />
                {isLoading ? 'Redirecting…' : 'Sign in with Google'}
              </Button>
            </VStack>
          </Box>
        </Flex>
      </Container>
    </Box>
  )
}

function GoogleIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <g fill="none">
        <path
          d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
          fill="#4285F4"
        />
        <path
          d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
          fill="#34A853"
        />
        <path
          d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
          fill="#FBBC05"
        />
        <path
          d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"
          fill="#EA4335"
        />
      </g>
    </svg>
  )
}

export default LoginPage
