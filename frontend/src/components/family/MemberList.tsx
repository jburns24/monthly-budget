import { useState } from 'react'
import { Badge, Box, Button, Flex, Heading, Text } from '@chakra-ui/react'
import type { FamilyMember } from '../../types/family'
import RoleChangeDialog from './RoleChangeDialog'
import RemoveMemberDialog from './RemoveMemberDialog'

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
  familyId: string
  isAdmin: boolean
  ownerId: string
}

function MemberList({ members, currentUserId, familyId, isAdmin, ownerId }: MemberListProps) {
  const [roleTarget, setRoleTarget] = useState<FamilyMember | null>(null)
  const [removeTarget, setRemoveTarget] = useState<FamilyMember | null>(null)

  return (
    <Box>
      <Heading as="h3" size="md" mb={3}>
        Members
      </Heading>
      <Flex direction="column" gap={3}>
        {members.map((member) => {
          const isSelf = member.user_id === currentUserId
          const isOwner = member.user_id === ownerId
          const canManage = isAdmin && !isSelf && !isOwner

          return (
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
                  {isSelf && ' (you)'}
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
                {isOwner ? 'Owner' : member.role === 'admin' ? 'Admin' : 'Member'}
              </Badge>
              {canManage && (
                <Flex gap={1}>
                  <Button size="xs" variant="ghost" onClick={() => setRoleTarget(member)}>
                    {member.role === 'admin' ? 'Demote' : 'Promote'}
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    colorPalette="red"
                    onClick={() => setRemoveTarget(member)}
                  >
                    Remove
                  </Button>
                </Flex>
              )}
            </Flex>
          )
        })}
      </Flex>

      {roleTarget && (
        <RoleChangeDialog
          member={roleTarget}
          familyId={familyId}
          open={roleTarget !== null}
          onClose={() => setRoleTarget(null)}
        />
      )}

      {removeTarget && (
        <RemoveMemberDialog
          member={removeTarget}
          familyId={familyId}
          open={removeTarget !== null}
          onClose={() => setRemoveTarget(null)}
        />
      )}
    </Box>
  )
}

export default MemberList
