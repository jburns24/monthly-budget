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
    <Flex direction="column" gap={3}>
      {categories.map((category) => (
        <Flex
          key={category.id}
          align="center"
          p={4}
          borderWidth="1px"
          borderRadius="md"
          borderColor="gray.200"
          gap={3}
          _hover={{ borderColor: 'brand.300', bg: 'gray.50' }}
          transition="border-color 0.15s, background-color 0.15s"
        >
          {/* Emoji icon */}
          <Flex
            align="center"
            justify="center"
            w="40px"
            h="40px"
            borderRadius="md"
            bg="brand.50"
            flexShrink={0}
            fontSize="xl"
            aria-hidden="true"
          >
            {category.icon ?? '📁'}
          </Flex>

          {/* Name */}
          <Box flex={1} minW={0}>
            <Text fontWeight="medium" truncate>
              {category.name}
            </Text>
            <Text fontSize="xs" color="gray.400">
              Order: {category.sort_order}
            </Text>
          </Box>

          {/* Active badge */}
          <Box
            px={2}
            py={0.5}
            borderRadius="full"
            bg={category.is_active ? 'green.100' : 'gray.100'}
            color={category.is_active ? 'green.700' : 'gray.500'}
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
                variant="ghost"
                colorPalette="brand"
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
    </Flex>
  )
}

export default CategoryList
