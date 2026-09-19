# Frontend image: the production bundle, served by nginx.
FROM node:20-alpine AS build

WORKDIR /app

# The lockfile is copied first so `npm ci` is cached independently of source
# changes. `npm ci` rather than `install` so the build is reproducible.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Baked in at build time: Create React App inlines REACT_APP_* variables.
ARG REACT_APP_API_URL=http://localhost:8000
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
