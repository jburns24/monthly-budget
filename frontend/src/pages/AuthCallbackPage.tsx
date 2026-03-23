import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Container, Spinner, Text, VStack } from '@chakra-ui/react'
import { postAuthCallback } from '../api/auth'

function AuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Read sessionStorage once at mount via lazy state initializer
  const [session] = useState(() => ({
    storedState: sessionStorage.getItem('oauth_state'),
    codeVerifier: sessionStorage.getItem('pkce_code_verifier'),
  }))

  const [asyncError, setAsyncError] = useState<string | null>(null)
  const hasRun = useRef(false)

  const code = searchParams.get('code')
  const state = searchParams.get('state')
  const errorParam = searchParams.get('error')

  // Derive all synchronous validation errors at render time (no setState in effect)
  const validationError: string | null = errorParam
    ? `Google sign-in was cancelled or denied: ${errorParam}`
    : !code || !state
      ? 'Missing authorization code or state parameter.'
      : state !== session.storedState
        ? 'State mismatch — possible CSRF attack. Please try signing in again.'
        : !session.codeVerifier
          ? 'Missing PKCE code verifier. Please try signing in again.'
          : null

  useEffect(() => {
    // Only proceed if no validation error and we haven't already fired
    if (validationError !== null || !code || !session.codeVerifier || hasRun.current) return
    hasRun.current = true

    // Consume PKCE/state values to prevent replay
    sessionStorage.removeItem('oauth_state')
    sessionStorage.removeItem('pkce_code_verifier')

    const safeCode = code
    const safeCv = session.codeVerifier

    postAuthCallback(safeCode, safeCv)
      .then(({ is_new_user }) => {
        navigate(is_new_user ? '/?new=true' : '/', { replace: true })
      })
      .catch((err: unknown) => {
        // setState in async callback is allowed by react-hooks/set-state-in-effect
        const msg = err instanceof Error ? err.message : 'Authentication failed. Please try again.'
        setAsyncError(msg)
      })
  }, [validationError, code, session.codeVerifier, navigate])

  const error = validationError ?? asyncError

  if (error !== null) {
    return (
      <Container maxW="md" py={16}>
        <VStack spacing={4} align="center">
          <Text color="red.500" fontSize="lg" fontWeight="semibold">
            Sign In Failed
          </Text>
          <Text color="gray.600" textAlign="center">
            {error}
          </Text>
          <Text>
            <a href="/login" style={{ color: '#3182ce', textDecoration: 'underline' }}>
              Return to sign in
            </a>
          </Text>
        </VStack>
      </Container>
    )
  }

  return (
    <Container maxW="md" py={16}>
      <VStack spacing={4} align="center">
        <Spinner size="xl" />
        <Text color="gray.600">Signing you in…</Text>
      </VStack>
    </Container>
  )
}

export default AuthCallbackPage
