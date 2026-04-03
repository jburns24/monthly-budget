import { Container } from '@chakra-ui/react'
import { useFamilyContext } from '../contexts/FamilyContext'
import CreateFamilyView from '../components/family/CreateFamilyView'
import FamilyDashboardView from '../components/family/FamilyDashboardView'

function FamilyPage() {
  const { familyId } = useFamilyContext()

  if (familyId === null) {
    return (
      <Container maxW="container.md" py={8}>
        <CreateFamilyView />
      </Container>
    )
  }

  return <FamilyDashboardView />
}

export default FamilyPage
