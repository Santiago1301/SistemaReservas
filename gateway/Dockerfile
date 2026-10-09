FROM node:22-slim

WORKDIR /app

# npm ci instala exactamente las versiones del package-lock.json.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY src ./src

# El proceso no corre como root dentro del contenedor.
USER node

CMD ["node", "src/index.js"]
