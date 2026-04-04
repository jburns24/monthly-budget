import { Box, Button, Container, Flex, Text } from '@chakra-ui/react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import type { User } from '../hooks/useAuth'

function UserAvatar({ user }: { user: User }) {
  const initials = user.display_name
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)

  return (
    <Box
      w={8}
      h={8}
      borderRadius="full"
      overflow="hidden"
      bg="teal.500"
      display="flex"
      alignItems="center"
      justifyContent="center"
      flexShrink={0}
    >
      {user.avatar_url !== null ? (
        <img
          src={user.avatar_url}
          alt={user.display_name}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      ) : (
        <Text color="white" fontSize="xs" fontWeight="bold" lineHeight={1}>
          {initials}
        </Text>
      )}
    </Box>
  )
}

function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async (): Promise<void> => {
    await logout()
    navigate('/login', { replace: true })
  }

  if (!user) return null

  return (
    <Box as="header" bg="brand.500" py={3}>
      <Container maxW="container.xl">
        <Flex align="center" justify="space-between">
          <Text fontWeight="bold" fontSize="lg" color="white" letterSpacing="-0.2px">
            Monthly Budget
          </Text>
          <Flex align="center" gap={3}>
            <UserAvatar user={user} />
            <Text fontSize="sm" color="whiteAlpha.900">
              {user.display_name}
            </Text>
            <Button
              size="sm"
              variant="ghost"
              color="white"
              _hover={{ bg: 'whiteAlpha.200' }}
              onClick={() => void handleLogout()}
            >
              Sign out
            </Button>
          </Flex>
        </Flex>
      </Container>
    </Box>
  )
}

export default Header
