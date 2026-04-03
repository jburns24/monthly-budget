import { Box, Button, Flex, Heading, Spinner, Text } from '@chakra-ui/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getPendingInvites, respondToInvite } from '../../api/family'
import { toaster } from '../ui/toaster'

function PendingInvites() {
  const queryClient = useQueryClient()

  const {
    data: invites,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['pendingInvites'],
    queryFn: getPendingInvites,
  })

  const respondMutation = useMutation({
    mutationFn: ({ inviteId, action }: { inviteId: string; action: 'accept' | 'decline' }) =>
      respondToInvite(inviteId, action),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pendingInvites'] })
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
      queryClient.invalidateQueries({ queryKey: ['family'] })
      toaster.create({
        title: variables.action === 'accept' ? 'Invite accepted' : 'Invite declined',
        description:
          variables.action === 'accept'
            ? 'You have joined the family.'
            : 'The invite has been declined.',
        type: 'success',
        duration: 4000,
      })
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to respond to invite. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" py={4}>
        <Spinner size="sm" />
      </Box>
    )
  }

  if (error || !invites) {
    return null
  }

  const pending = invites.filter((inv) => inv.status === 'pending')

  if (pending.length === 0) {
    return null
  }

  return (
    <Box mt={6}>
      <Heading as="h3" size="md" mb={3}>
        Pending Invites
      </Heading>
      <Flex direction="column" gap={3}>
        {pending.map((invite) => (
          <Flex
            key={invite.id}
            align="center"
            p={3}
            borderWidth="1px"
            borderRadius="md"
            borderColor="gray.200"
            gap={3}
          >
            <Box flex={1} minW={0}>
              <Text fontWeight="medium" truncate>
                {invite.family_name}
              </Text>
              <Text fontSize="sm" color="gray.500" truncate>
                Invited by {invite.invited_by_display_name}
              </Text>
            </Box>
            <Flex gap={2}>
              <Button
                size="sm"
                colorPalette="green"
                onClick={() => respondMutation.mutate({ inviteId: invite.id, action: 'accept' })}
                loading={respondMutation.isPending}
              >
                Accept
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => respondMutation.mutate({ inviteId: invite.id, action: 'decline' })}
                loading={respondMutation.isPending}
              >
                Decline
              </Button>
            </Flex>
          </Flex>
        ))}
      </Flex>
    </Box>
  )
}

export default PendingInvites
