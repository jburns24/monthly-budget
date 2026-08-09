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
      bg="surface.2"
      borderWidth="1px"
      borderColor="hairline"
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
        <Text color="ink" fontSize="xs" fontWeight="medium" lineHeight={1}>
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
    <Box
      as="header"
      position="sticky"
      top={0}
      zIndex="sticky"
      bg="rgba(8, 8, 8, 0.88)"
      borderBottomWidth="1px"
      borderColor="hairline.soft"
      backdropFilter="blur(18px)"
    >
      <Container maxW="1200px" px={{ base: 4, md: 8 }}>
        <Flex align="center" justify="space-between" h="64px">
          <Text
            fontFamily="heading"
            fontWeight="500"
            fontSize="lg"
            color="ink"
            letterSpacing="-0.8px"
          >
            Monthly<span style={{ color: '#999' }}>.</span>Budget
          </Text>
          <Flex align="center" gap={{ base: 2, md: 3 }}>
            <UserAvatar user={user} />
            <Text
              display={{ base: 'none', md: 'block' }}
              fontSize="sm"
              color="ink.muted"
              letterSpacing="-0.14px"
            >
              {user.display_name}
            </Text>
            <Button
              size="sm"
              bg="surface.1"
              color="ink"
              borderRadius="pill"
              px={4}
              minH="40px"
              fontWeight="500"
              _hover={{ bg: 'surface.2' }}
              _active={{ transform: 'scale(0.97)' }}
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
