FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY index.html main.jsx IncidentMap.jsx style.css vite.config.js ./
ARG VITE_MAP_TILE_URL
ENV VITE_MAP_TILE_URL=$VITE_MAP_TILE_URL
RUN npm run build
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
