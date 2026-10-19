# Frontend — AGENTS.md

React 19 + TypeScript + Vite, Chakra UI v3 + Emotion (+ `@chakra-ui/charts`), React Router v7,
TanStack Query. Visual language: [DESIGN.md](../DESIGN.md).

## Commands (from `frontend/`)

```bash
npm run test:run       # Vitest, single run (task fe:test); npm test = watch
npm run lint           # ESLint
npm run format         # Prettier write (format:check to verify)
npx tsc -b             # Type check (task fe:typecheck). Plain `tsc --noEmit` checks nothing: the root tsconfig only has references
npm run build          # tsc -b && vite build
```

## Layout

- `src/main.tsx` mounts; `src/App.tsx` defines routes. Authenticated pages are wrapped in
  `ProtectedRoute` + `ProtectedLayout` (`FamilyProvider`, `BottomNavigation`); `Header` renders on every route, including `/login`.
- `src/pages/` route components; `src/components/<domain>/` (assets, categories, dashboard,
  expenses, family, goals, recurring, `ui/toaster`).
- `src/api/*.ts` — typed calls per domain, all through `apiClient` in `api/client.ts`
  (credentials included; on 401 it calls `/api/auth/refresh` once, queues concurrent requests,
  and redirects to `/login` if refresh fails unless `redirectOnAuthFailure: false`).
- `src/types/*.ts` — hand-written API types. Keep them in sync with
  [docs/api-contract.md](../docs/api-contract.md) (generated from the backend).
- `src/hooks/` (`useAuth`, `useAssets`, `useOnlineStatus`), `src/contexts/FamilyContext`
  (`useFamilyContext`), `src/utils/`, `src/theme.ts` (Chakra system).

## Patterns

- Server state via React Query: `useQuery` for reads, `useMutation` for writes, invalidate the
  affected keys after a mutation.
- All requests are relative `/api/...`. In dev, Vite proxies `/api` to `VITE_DEV_PROXY_TARGET`
  (default `http://localhost:8000`); under k3d the Traefik ingress makes it same-origin. The
  production nginx image does **not** proxy `/api`; the ingress does.
- `VITE_*` env vars are inlined at build time (`VITE_GOOGLE_CLIENT_ID` is a Docker build arg).
- `@/` aliases `src/`; existing code mixes it with relative imports — match the file you edit.
- Category auto-suggest (`CreateExpenseDialog`): on Description blur (≥ 3 chars, expense type)
  call `suggestCategory`, abort stale requests, and never override a category the user picked
  in this dialog session.

## Testing

- Vitest + Testing Library, `happy-dom`, setup in `src/setupTests.ts` (jest-dom matchers);
  `@chakra-ui` and `framer-motion` are inlined in `vite.config.ts`.
- All tests live in `src/__tests__/`. Wrap renders in `ChakraProvider value={system}`,
  `QueryClientProvider`, `MemoryRouter`, and `FamilyProvider` as needed — copy an existing test.
- Mock with `vi.mock('../api/...')` / `vi.mock('../hooks/useAuth')`; a never-resolving promise
  gives a loading state. When a module gains an export, add it to every mock of that module.
- Dialogs auto-focus a field after a short delay; wait for that focus before typing elsewhere or
  the focus jump makes tests flaky.

## Hard stops

- NEVER add a raw `fetch()` outside `src/api/client.ts` — use the API layer. (Existing exceptions: the logout call in `hooks/useAuth.ts` and the health probe in `pages/HomePage.tsx`.)
- NEVER render Chakra components in tests without `ChakraProvider`.
- NEVER inline types that belong in `src/types/`.
- NEVER use `any` without a reason; prefer `unknown` or a real type.
