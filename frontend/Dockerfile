FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# Reproducible installation from the committed npm lockfile.
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Scout recommends this smaller Nginx variant. It still has reported CVEs:
# check actual results with Docker Scout after rebuilding.
FROM nginx:1.31-alpine-slim
RUN apk upgrade --no-cache
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
