import { Box, Container, Heading, Text } from '@chakra-ui/react'

function FamilyPage() {
  return (
    <Container maxW="container.md" py={8}>
      <Box>
        <Heading as="h1" size="xl" mb={4}>
          Family
        </Heading>
        <Text color="gray.600">Family management coming soon.</Text>
      </Box>
    </Container>
  )
}

export default FamilyPage
