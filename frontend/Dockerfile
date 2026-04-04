# Dev stage: install deps in image, mount source at runtime for HMR
FROM node:22-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json ./
# Remove lockfile and reinstall to get correct platform-specific bindings
# (lockfile generated on macOS won't resolve linux native modules correctly)
RUN rm package-lock.json && npm install
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build stage: full source copy + production build
FROM dev AS build
COPY . .
RUN npm run build
