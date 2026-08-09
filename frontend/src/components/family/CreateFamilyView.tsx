import { useState } from 'react'
import {
  Box,
  Button,
  Card,
  Heading,
  Input,
  NativeSelectField,
  NativeSelectRoot,
  Text,
} from '@chakra-ui/react'
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
    <Box display="flex" justifyContent="center" pt={{ base: 6, md: 12 }}>
      <Card.Root
        maxW="520px"
        w="full"
        bg="surface.1"
        borderWidth="1px"
        borderColor="hairline"
        borderRadius="spotlight"
        p={{ base: 2, md: 4 }}
        boxShadow="0 24px 60px rgba(0,0,0,0.3)"
      >
        <Card.Header>
          <Heading
            as="h1"
            fontFamily="heading"
            fontSize={{ base: '38px', md: '52px' }}
            fontWeight="500"
            lineHeight="0.98"
            letterSpacing={{ base: '-1.9px', md: '-2.6px' }}
            textAlign="center"
          >
            Create your family
          </Heading>
          <Text color="ink.muted" textAlign="center" mt={3}>
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
                bg="surface.2"
                borderColor="hairline"
                borderRadius="10px"
                minH="44px"
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
              <NativeSelectRoot>
                <NativeSelectField
                  bg="surface.2"
                  borderColor="hairline"
                  borderRadius="10px"
                  minH="44px"
                  id="timezone"
                  name="timezone"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                >
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz.replace(/_/g, ' ')}
                    </option>
                  ))}
                </NativeSelectField>
              </NativeSelectRoot>
            </Box>
            <Button
              type="submit"
              colorPalette="brand"
              borderRadius="pill"
              minH="44px"
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
