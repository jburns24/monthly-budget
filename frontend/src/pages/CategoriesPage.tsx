import { useState } from 'react'
import { Box, Button, Container, Flex, Heading, Spinner, Text } from '@chakra-ui/react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useFamilyContext } from '../contexts/FamilyContext'
import { getCategories, seedCategories } from '../api/categories'
import type { Category } from '../types/categories'
import CategoryList from '../components/categories/CategoryList'
import CreateCategoryDialog from '../components/categories/CreateCategoryDialog'
import EditCategoryDialog from '../components/categories/EditCategoryDialog'
import ArchiveCategoryDialog from '../components/categories/ArchiveCategoryDialog'
import { toaster } from '../components/ui/toaster'

function CategoriesPage() {
  const { familyId, role } = useFamilyContext()
  const queryClient = useQueryClient()
  const isAdmin = role === 'admin'

  const [createOpen, setCreateOpen] = useState(false)
  const [editCategory, setEditCategory] = useState<Category | null>(null)
  const [archiveCategory, setArchiveCategory] = useState<Category | null>(null)

  const {
    data: categories,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId!),
    enabled: familyId !== null,
  })

  const seedMutation = useMutation({
    mutationFn: () => seedCategories(familyId!),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['categories', familyId] })
      toaster.create({
        title: 'Default categories added',
        description: `${data.created_count} categories have been seeded.`,
        type: 'success',
        duration: 4000,
      })
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to seed categories. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  return (
    <Container maxW="container.md" py={8}>
      <Flex align="center" justify="space-between" mb={6}>
        <Heading size="lg">Categories</Heading>
        {isAdmin && (
          <Button colorPalette="brand" size="sm" onClick={() => setCreateOpen(true)}>
            Add Category
          </Button>
        )}
      </Flex>

      {isLoading && (
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading categories" />
        </Flex>
      )}

      {isError && (
        <Box py={8} textAlign="center">
          <Text color="red.500">Failed to load categories. Please refresh the page.</Text>
        </Box>
      )}

      {categories && (
        <>
          {isAdmin && categories.length === 0 && (
            <Box mb={4} textAlign="center">
              <Button
                variant="outline"
                colorPalette="brand"
                size="sm"
                onClick={() => seedMutation.mutate()}
                loading={seedMutation.isPending}
              >
                Seed defaults
              </Button>
            </Box>
          )}
          <CategoryList
            categories={categories}
            onEdit={(category) => setEditCategory(category)}
            onDelete={(category) => setArchiveCategory(category)}
          />
        </>
      )}

      {familyId && (
        <>
          <CreateCategoryDialog
            open={createOpen}
            onOpenChange={setCreateOpen}
            familyId={familyId}
          />
          <EditCategoryDialog
            open={editCategory !== null}
            onOpenChange={(open) => {
              if (!open) setEditCategory(null)
            }}
            familyId={familyId}
            category={editCategory}
          />
          <ArchiveCategoryDialog
            open={archiveCategory !== null}
            onOpenChange={(open) => {
              if (!open) setArchiveCategory(null)
            }}
            familyId={familyId}
            category={archiveCategory}
          />
        </>
      )}
    </Container>
  )
}

export default CategoriesPage
