# Etapa 1: compila la aplicación a archivos estáticos.
FROM node:22-slim AS compilacion
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Dirección del gateway vista desde el navegador del usuario.
ARG VITE_GATEWAY_URL=http://localhost:4000/graphql
ENV VITE_GATEWAY_URL=$VITE_GATEWAY_URL
RUN npm run build

# Etapa 2: la imagen final solo lleva nginx y los archivos ya compilados.
FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=compilacion /app/dist /usr/share/nginx/html
