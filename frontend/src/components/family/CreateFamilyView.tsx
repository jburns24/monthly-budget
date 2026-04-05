import { useState } from 'react'
import { Box, Button, Card, Heading, Input, Text } from '@chakra-ui/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFamily } from '../../api/family'
import { toaster } from '../ui/toaster'

const TIMEZONE_OPTIONS = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Australia/Sydney',
  'UTC',
]

function CreateFamilyView() {
  const [name, setName] = useState('')
  const [timezone, setTimezone] = useState('America/New_York')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => createFamily(name.trim(), timezone),
    onSuccess: () => {
      toaster.create({
        title: 'Family created',
        description: 'Your family has been created successfully.',
        type: 'success',
        duration: 4000,
      })
      void queryClient.invalidateQueries({ queryKey: ['currentUser'] })
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to create family. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (name.trim().length === 0) return
    mutation.mutate()
  }

  return (
    <Box display="flex" justifyContent="center" pt={12}>
      <Card.Root maxW="md" w="full" borderTopWidth="3px" borderTopColor="teal.500">
        <Card.Header>
          <Heading as="h2" size="lg" textAlign="center">
            Create Your Family
          </Heading>
          <Text color="gray.500" textAlign="center" mt={2}>
            Start managing your household budget together.
          </Text>
        </Card.Header>
        <Card.Body>
          <form onSubmit={handleSubmit}>
            <Box mb={4}>
              <Text fontWeight="medium" mb={1}>
                Family Name
              </Text>
              <Input
                id="family-name"
                name="family-name"
                placeholder="e.g. The Smiths"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </Box>
            <Box mb={6}>
              <Text fontWeight="medium" mb={1}>
                Timezone
              </Text>
              <Box
                as="select"
                id="timezone"
                name="timezone"
                w="full"
                h="40px"
                px={3}
                borderWidth="1px"
                borderRadius="md"
                borderColor="gray.200"
                bg="white"
                value={timezone}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setTimezone(e.target.value)}
              >
                {TIMEZONE_OPTIONS.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz.replace(/_/g, ' ')}
                  </option>
                ))}
              </Box>
            </Box>
            <Button
              type="submit"
              colorPalette="brand"
              w="full"
              loading={mutation.isPending}
              disabled={name.trim().length === 0}
            >
              Create Family
            </Button>
          </form>
        </Card.Body>
      </Card.Root>
    </Box>
  )
}

export default CreateFamilyView
