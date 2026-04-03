import { Box, Container, Heading, Spinner, Text } from '@chakra-ui/react'
import { useQuery } from '@tanstack/react-query'
import { getFamily } from '../../api/family'
import { useFamilyContext } from '../../contexts/FamilyContext'
import { useAuth } from '../../hooks/useAuth'
import MemberList from './MemberList'
import InviteForm from './InviteForm'
import PendingInvites from './PendingInvites'
import LeaveButton from './LeaveButton'

function FamilyDashboardView() {
  const { familyId, role } = useFamilyContext()
  const { user } = useAuth()

  const {
    data: family,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['family', familyId],
    queryFn: () => getFamily(familyId!),
    enabled: familyId !== null,
  })

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" py={12}>
        <Spinner size="lg" />
      </Box>
    )
  }

  if (error || !family) {
    return (
      <Box py={8}>
        <Text color="red.500">Failed to load family details. Please try again.</Text>
      </Box>
    )
  }

  const isAdmin = role === 'admin'
  const currentUserId = user?.id ?? ''
  const isOwner = family.created_by === currentUserId

  return (
    <Container maxW="container.md" py={8}>
      <Heading as="h1" size="xl" mb={6}>
        {family.name}
      </Heading>
      <PendingInvites />
      <MemberList
        members={family.members}
        currentUserId={currentUserId}
        familyId={family.id}
        isAdmin={isAdmin}
        ownerId={family.created_by}
      />
      {isAdmin && <InviteForm familyId={family.id} />}
      {!isOwner && <LeaveButton familyId={family.id} familyName={family.name} />}
    </Container>
  )
}

export default FamilyDashboardView
