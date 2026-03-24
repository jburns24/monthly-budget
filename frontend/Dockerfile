FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./

# Remove lockfile and reinstall to get correct platform-specific bindings
# (lockfile generated on macOS won't resolve linux native modules correctly)
RUN rm package-lock.json && npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
