import { useQuery } from '@tanstack/react-query'
import { Box, Container, Heading, Text, Spinner, VStack } from '@chakra-ui/react'
import { useAuth } from '../hooks/useAuth'
import PendingInvites from '../components/family/PendingInvites'

interface HealthResponse {
  status: string
}

function HomePage() {
  const { isAuthenticated } = useAuth()

  const { data, isLoading, error } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: async () => {
      const response = await fetch('/api/health')
      if (!response.ok) {
        throw new Error('Health check failed')
      }
      return response.json()
    },
  })

  return (
    <Container maxW="container.md" py={8}>
      <VStack spacing={6} align="start">
        <Heading as="h1" size="2xl">
          Monthly Budget
        </Heading>
        <Text fontSize="lg">Frontend is running.</Text>
        <Box>
          {isLoading && <Spinner />}
          {error && <Text color="red.500">API health: Error</Text>}
          {data && <Text color="green.500">API health: {data.status}</Text>}
        </Box>
        {isAuthenticated && <PendingInvites />}
      </VStack>
    </Container>
  )
}

export default HomePage
