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
    <Container maxW="1199px" px={{ base: 4, md: 8 }} py={{ base: 8, md: 16 }}>
      <Text
        color="ink.muted"
        fontSize="13px"
        fontWeight="500"
        textTransform="uppercase"
        letterSpacing="0.08em"
        mb={3}
      >
        Household
      </Text>
      <Heading
        as="h1"
        mb={{ base: 8, md: 12 }}
        color="ink"
        fontFamily="heading"
        fontSize={{ base: '48px', md: '85px' }}
        fontWeight="500"
        lineHeight="0.95"
        letterSpacing={{ base: '-2.4px', md: '-4.25px' }}
      >
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
