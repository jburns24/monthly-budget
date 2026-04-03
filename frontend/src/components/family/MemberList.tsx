import { Badge, Box, Flex, Heading, Text } from '@chakra-ui/react'
import type { FamilyMember } from '../../types/family'

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

interface MemberListProps {
  members: FamilyMember[]
  currentUserId: string
}

function MemberList({ members }: MemberListProps) {
  return (
    <Box>
      <Heading as="h3" size="md" mb={3}>
        Members
      </Heading>
      <Flex direction="column" gap={3}>
        {members.map((member) => (
          <Flex
            key={member.user_id}
            align="center"
            p={3}
            borderWidth="1px"
            borderRadius="md"
            borderColor="gray.200"
            gap={3}
          >
            <Flex
              align="center"
              justify="center"
              w="40px"
              h="40px"
              borderRadius="full"
              bg="blue.100"
              color="blue.700"
              fontWeight="bold"
              fontSize="sm"
              flexShrink={0}
            >
              {member.avatar_url ? (
                <Box
                  as="img"
                  src={member.avatar_url}
                  alt={member.display_name}
                  w="40px"
                  h="40px"
                  borderRadius="full"
                  objectFit="cover"
                />
              ) : (
                getInitials(member.display_name)
              )}
            </Flex>
            <Box flex={1} minW={0}>
              <Text fontWeight="medium" truncate>
                {member.display_name}
              </Text>
              <Text fontSize="sm" color="gray.500" truncate>
                {member.email}
              </Text>
            </Box>
            <Badge
              colorPalette={member.role === 'admin' ? 'purple' : 'gray'}
              variant="subtle"
              size="sm"
            >
              {member.role === 'admin' ? 'Admin' : 'Member'}
            </Badge>
          </Flex>
        ))}
      </Flex>
    </Box>
  )
}

export default MemberList
