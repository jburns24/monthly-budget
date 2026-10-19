import { Text } from '@chakra-ui/react'
import { useQuery } from '@tanstack/react-query'
import { WEB_VERSION, getApiVersion } from '../api/version'
import { formatVersion } from '../utils/format'

/** Muted one-line footer: "web v0.11.0 · api v0.12.0". */
export default function AppVersion() {
  const { data, isError } = useQuery({
    queryKey: ['api-version'],
    queryFn: getApiVersion,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const api = data ? formatVersion(data.version) : isError ? '?' : '…'

  return (
    <Text
      data-testid="app-version"
      fontSize="xs"
      color="ink.muted"
      textAlign="center"
      py={3}
      userSelect="text"
    >
      web {formatVersion(WEB_VERSION)} · api {api}
    </Text>
  )
}
