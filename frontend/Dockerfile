FROM node:20-alpine AS build
WORKDIR /app

# Copy lockfile first so the layer is only rebuilt on dependency changes
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ || exit 1
