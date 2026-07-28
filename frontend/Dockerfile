# Dev stage: install deps in image, mount source at runtime for HMR
FROM node:22-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json ./
# Remove lockfile and reinstall to get correct platform-specific bindings
# (lockfile generated on macOS won't resolve linux native modules correctly)
RUN rm package-lock.json && npm install
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build stage: production build against the pinned lockfile.
# Uses a fresh install (not the dev stage's floating `npm install`) so the
# published image matches what CI/local reproducibly resolve.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
# Vite inlines VITE_* vars at build time, so they must be present here
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
COPY . .
RUN npm run build

# ============================================================
# Runtime stage: nginx serving the static bundle
# /api is NOT proxied here — the deploy layer (ingress / reverse proxy)
# routes /api to the backend service.
# ============================================================
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
