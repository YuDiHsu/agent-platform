FROM node:22-alpine
WORKDIR /app

COPY apps/web-portal/package.json apps/web-portal/package-lock.json ./
RUN npm ci

COPY apps/web-portal ./
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
