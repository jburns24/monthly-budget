# Frontend — CLAUDE.md

React 19 + TypeScript + Vite, with Chakra UI v3 + Emotion, React Router v7, TanStack React Query.

## Commands

```bash
npm run test:run       # Run all tests (single run)
npm test               # Tests in watch mode
npm run lint           # ESLint
npm run format         # Prettier auto-format
npm run format:check   # Prettier check
npx tsc --noEmit       # Type check
```

## Architecture

- **Entry**: `src/main.tsx` mounts the app; `src/App.tsx` defines routes with `ProtectedRoute`
- **Pages**: `src/pages/` — route-level components (Dashboard, Expenses, Categories, Family, Login, etc.)
- **Components**: `src/components/` — organized by domain (goals/, expenses/, family/)
- **API layer**: `src/api/` — typed fetch functions per domain (auth, categories, client, expenses, family, goals)
- **State**: React Query for server state, `src/contexts/FamilyContext` for shared family context
- **Hooks**: `src/hooks/` — custom hooks (useAuth, useFamily, etc.)
- **Types**: `src/types/` — centralized TypeScript type definitions per domain
- **Theme**: `src/theme.ts` — Chakra UI v3 system configuration

## Critical Patterns

**Path alias**: `@/` maps to `src/` (configured in vite.config.ts and tsconfig.app.json). Always use `@/` for imports.

**API proxy**: Vite proxies `/api` to `http://localhost:8000` in dev. The API layer in `src/api/client.ts` uses relative `/api/...` paths.

**React Query conventions**: Data fetching uses TanStack Query. Use `useQuery` for reads, `useMutation` for writes. Invalidate relevant query keys after mutations.

## Testing

- **Framework**: Vitest + React Testing Library + happy-dom environment
- **Setup**: `src/setupTests.ts` imports `@testing-library/jest-dom` for matchers
- **Chakra + Framer**: `@chakra-ui` and `framer-motion` are inlined in test deps (see `vite.config.ts`)
- **Render wrapper**: Tests wrap components in `<ChakraProvider value={system}>`, `<QueryClientProvider>`, `<MemoryRouter>`, and `<FamilyProvider>` as needed. Check existing tests for the exact pattern.
- **Mocking pattern**: Use `vi.mock('../hooks/useAuth')` and `vi.mock('../api/...')` to stub API calls. Return `new Promise(() => {})` for loading states, or resolved values for data states.
- **Test location**: All tests live in `src/__tests__/` — not colocated with components

## Hard Stops

- NEVER use bare `fetch()` — use the API layer in `src/api/` or React Query
- NEVER skip the ChakraProvider wrapper in tests — Chakra components crash without it
- NEVER inline TypeScript types that belong in `src/types/` — extend existing type files
- NEVER use `any` without justification — prefer `unknown` or proper typing
