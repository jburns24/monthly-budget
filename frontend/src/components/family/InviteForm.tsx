import { useState } from 'react'
import { Box, Button, Flex, Heading, Input } from '@chakra-ui/react'
import { useMutation } from '@tanstack/react-query'
import { sendInvite } from '../../api/family'
import { toaster } from '../ui/toaster'

interface InviteFormProps {
  familyId: string
}

function InviteForm({ familyId }: InviteFormProps) {
  const [email, setEmail] = useState('')

  const inviteMutation = useMutation({
    mutationFn: (inviteEmail: string) => sendInvite(familyId, inviteEmail),
    onSuccess: () => {
      toaster.create({
        title: 'Invite sent',
        description: 'If the user exists, they will receive your invitation.',
        type: 'success',
        duration: 4000,
      })
      setEmail('')
    },
    onError: () => {
      // Always show generic success to avoid leaking user existence
      toaster.create({
        title: 'Invite sent',
        description: 'If the user exists, they will receive your invitation.',
        type: 'success',
        duration: 4000,
      })
      setEmail('')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = email.trim()
    if (trimmed.length === 0) return
    inviteMutation.mutate(trimmed)
  }

  return (
    <Box mt={6}>
      <Heading as="h3" size="md" mb={3}>
        Invite Member
      </Heading>
      <form onSubmit={handleSubmit}>
        <Flex gap={3}>
          <Input
            type="email"
            placeholder="Enter email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            flex={1}
          />
          <Button
            type="submit"
            colorPalette="brand"
            loading={inviteMutation.isPending}
            disabled={email.trim().length === 0}
          >
            Send Invite
          </Button>
        </Flex>
      </form>
    </Box>
  )
}

export default InviteForm
