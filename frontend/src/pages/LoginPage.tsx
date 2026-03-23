import { useState } from 'react'
import { Box, Button, Container, Heading, Text, VStack } from '@chakra-ui/react'
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
    <Container maxW="md" py={16}>
      <VStack spacing={8} align="center">
        <Heading as="h1" size="2xl" textAlign="center">
          Monthly Budget
        </Heading>
        <Text fontSize="lg" color="gray.600" textAlign="center">
          Sign in to manage your monthly budget
        </Text>
        <Box w="full" p={8} borderWidth="1px" borderRadius="lg" boxShadow="md">
          <VStack spacing={4}>
            {error !== null && (
              <Box
                w="full"
                p={3}
                bg="red.50"
                borderRadius="md"
                borderWidth="1px"
                borderColor="red.200"
                role="alert"
              >
                <Text color="red.700" fontSize="sm">
                  {error}
                </Text>
              </Box>
            )}
            <Button
              onClick={() => void handleSignIn()}
              disabled={isLoading}
              variant="outline"
              size="lg"
              w="full"
              borderColor="gray.300"
              gap={2}
            >
              <GoogleIcon />
              {isLoading ? 'Redirecting…' : 'Sign in with Google'}
            </Button>
          </VStack>
        </Box>
      </VStack>
    </Container>
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
