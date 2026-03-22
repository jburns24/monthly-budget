import { Routes, Route } from 'react-router-dom'
import { Box, Heading, Text } from '@chakra-ui/react'

function HomePage() {
  return (
    <Box p={8}>
      <Heading as="h1" size="xl" mb={4}>
        Monthly Budget
      </Heading>
      <Text>Welcome to Monthly Budget. Your dashboard is coming soon.</Text>
    </Box>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
    </Routes>
  )
}

export default App
