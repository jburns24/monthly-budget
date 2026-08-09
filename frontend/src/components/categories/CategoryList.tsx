import { Box, Button, Flex, Text } from '@chakra-ui/react'
import type { Category } from '../../types/categories'
import { useFamilyContext } from '../../contexts/FamilyContext'

interface CategoryListProps {
  categories: Category[]
  onEdit: (category: Category) => void
  onDelete: (category: Category) => void
}

function CategoryList({ categories, onEdit, onDelete }: CategoryListProps) {
  const { role } = useFamilyContext()
  const isAdmin = role === 'admin'

  if (categories.length === 0) {
    return (
      <Box py={8} textAlign="center">
        <Text color="gray.500">No categories yet. Add one to get started.</Text>
      </Box>
    )
  }

  return (
    <Box
      display="grid"
      gridTemplateColumns={{ base: '1fr', md: 'repeat(2, minmax(0, 1fr))' }}
      gap={3}
    >
      {categories.map((category) => (
        <Flex
          key={category.id}
          align="center"
          p={{ base: 4, md: 5 }}
          borderWidth="1px"
          borderRadius="card"
          borderColor="hairline"
          bg="surface.1"
          gap={3}
          _hover={{ borderColor: 'surface.3', bg: 'surface.2', transform: 'translateY(-2px)' }}
          transition="border-color 0.15s, background-color 0.15s, transform 0.15s"
        >
          {/* Emoji icon */}
          <Flex
            align="center"
            justify="center"
            w="40px"
            h="40px"
            borderRadius="10px"
            bg="surface.2"
            borderWidth="1px"
            borderColor="hairline"
            flexShrink={0}
            fontSize="xl"
            aria-hidden="true"
          >
            {category.icon ?? '📁'}
          </Flex>

          {/* Name */}
          <Box flex={1} minW={0}>
            <Text fontWeight="500" color="ink" truncate>
              {category.name}
            </Text>
            <Text fontSize="xs" color="ink.muted">
              Order: {category.sort_order}
            </Text>
          </Box>

          {/* Active badge */}
          <Box
            px={2}
            py={0.5}
            borderRadius="full"
            bg="surface.2"
            color={category.is_active ? 'ink' : 'ink.muted'}
            borderWidth="1px"
            borderColor="hairline"
            fontSize="xs"
            fontWeight="medium"
          >
            {category.is_active ? 'Active' : 'Archived'}
          </Box>

          {/* Admin-only controls */}
          {isAdmin && (
            <Flex gap={2} flexShrink={0}>
              <Button
                size="xs"
                color="ink"
                bg="surface.2"
                borderRadius="pill"
                onClick={() => onEdit(category)}
                aria-label={`Edit ${category.name}`}
              >
                Edit
              </Button>
              <Button
                size="xs"
                variant="ghost"
                colorPalette="red"
                onClick={() => onDelete(category)}
                aria-label={`Delete ${category.name}`}
              >
                Delete
              </Button>
            </Flex>
          )}
        </Flex>
      ))}
    </Box>
  )
}

export default CategoryList
