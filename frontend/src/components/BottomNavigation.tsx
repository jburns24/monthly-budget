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

function ExpensesIcon() {
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
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <line x1="2" y1="10" x2="22" y2="10" />
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
          direction={{ base: 'column', md: 'row' }}
          align="center"
          justify="center"
          flex={1}
          minH={{ base: '58px', md: '40px' }}
          px={{ base: 1, md: 3 }}
          color="ink.muted"
          cursor="not-allowed"
          aria-disabled="true"
          gap={{ base: 1, md: 2 }}
          opacity={0.45}
        >
          {icon}
          <Text fontSize="xs" fontWeight="medium" whiteSpace="nowrap">
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
          direction={{ base: 'column', md: 'row' }}
          align="center"
          justify="center"
          flex={1}
          minH={{ base: '58px', md: '40px' }}
          px={{ base: 1, md: 3 }}
          borderRadius={{ base: '14px', md: 'pill' }}
          bg={isActive ? 'surface.2' : 'transparent'}
          color={isActive ? 'ink' : 'ink.muted'}
          _hover={{ color: 'ink', bg: isActive ? 'surface.2' : 'surface.1' }}
          _active={{ transform: 'scale(0.97)' }}
          transition="color 0.15s, background-color 0.15s, transform 0.1s"
          gap={{ base: 1, md: 2 }}
        >
          {icon}
          <Text fontSize="xs" fontWeight="medium" whiteSpace="nowrap">
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
      top={{ base: 'auto', md: '10px' }}
      bottom={{ base: 0, md: 'auto' }}
      left={{ base: 0, md: '50%' }}
      right={{ base: 0, md: 'auto' }}
      transform={{ base: 'none', md: 'translateX(-50%)' }}
      zIndex="sticky"
      bg={{ base: 'rgba(18, 18, 18, 0.94)', md: 'surface.1' }}
      borderWidth="1px"
      borderColor="hairline"
      borderRadius={{ base: '20px 20px 0 0', md: 'pill' }}
      boxShadow={{ base: '0 -8px 30px rgba(0,0,0,0.35)', md: '0 12px 35px rgba(0,0,0,0.35)' }}
      backdropFilter="blur(18px)"
      p={{ base: 1, md: 1 }}
      w={{ base: '100%', md: 'auto' }}
      aria-label="Bottom navigation"
    >
      <Flex minW={{ base: 0, md: '540px' }}>
        <NavItem to="/" icon={<DashboardIcon />} label="Dashboard" />
        <NavItem to="/expenses" icon={<ExpensesIcon />} label="Expenses" />
        <NavItem to="/categories" icon={<CategoriesIcon />} label="Categories" />
        <NavItem to="/family" icon={<FamilyIcon />} label="Family" />
        <NavItem to="/settings" icon={<SettingsIcon />} label="Settings" disabled />
      </Flex>
    </Box>
  )
}

export default BottomNavigation
