FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
ENV VITE_API_BASE=/api
RUN npm run build

FROM nginx:1.27-alpine

ARG GIT_COMMIT=unknown
ARG BUILD_DATE
LABEL org.opencontainers.image.revision=$GIT_COMMIT \
      org.opencontainers.image.created=$BUILD_DATE

RUN apk add --no-cache python3 rsvg-convert font-dejavu
COPY --chmod=755 frontend/scripts/render-site-metadata.py /docker-entrypoint.d/40-site-metadata.sh

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:80/ || exit 1
