import { Box, Flex, Text } from '@chakra-ui/react'
import { NavLink } from 'react-router-dom'

function DashboardIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  )
}

function CategoriesIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  )
}

function FamilyIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function SettingsIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

interface NavItemProps {
  to: string
  icon: React.ReactNode
  label: string
  disabled?: boolean
}

function NavItem({ to, icon, label, disabled = false }: NavItemProps) {
  if (disabled) {
    return (
      <Box
        as="span"
        display="flex"
        flex={1}
        title="Coming soon"
        aria-label={`${label} (coming soon)`}
      >
        <Flex
          direction="column"
          align="center"
          justify="center"
          flex={1}
          py={2}
          color="gray.400"
          cursor="not-allowed"
          aria-disabled="true"
          gap={1}
        >
          {icon}
          <Text fontSize="xs" fontWeight="medium">
            {label}
          </Text>
        </Flex>
      </Box>
    )
  }

  return (
    <NavLink
      to={to}
      style={{ flex: 1, display: 'flex', textDecoration: 'none' }}
      aria-label={label}
    >
      {({ isActive }: { isActive: boolean }) => (
        <Flex
          direction="column"
          align="center"
          justify="center"
          flex={1}
          py={2}
          color={isActive ? 'brand.500' : 'gray.500'}
          _hover={{ color: isActive ? 'brand.500' : 'teal.600' }}
          gap={1}
        >
          {icon}
          <Text fontSize="xs" fontWeight={isActive ? 'semibold' : 'medium'}>
            {label}
          </Text>
        </Flex>
      )}
    </NavLink>
  )
}

function BottomNavigation() {
  return (
    <Box
      as="nav"
      position="fixed"
      bottom={0}
      left={0}
      right={0}
      zIndex="sticky"
      bg="white"
      borderTopWidth="1px"
      borderColor="gray.200"
      aria-label="Bottom navigation"
    >
      <Flex>
        <NavItem to="/" icon={<DashboardIcon />} label="Dashboard" />
        <NavItem to="/categories" icon={<CategoriesIcon />} label="Categories" />
        <NavItem to="/family" icon={<FamilyIcon />} label="Family" />
        <NavItem to="/settings" icon={<SettingsIcon />} label="Settings" disabled />
      </Flex>
    </Box>
  )
}

export default BottomNavigation
