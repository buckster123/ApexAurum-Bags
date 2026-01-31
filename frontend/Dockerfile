# ApexAurum Cloud - Frontend Production Dockerfile
# Note: Railway uses rootDirectory=frontend, so paths are relative to frontend/
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (relative to frontend/)
COPY package*.json ./
RUN npm install

# VITE_API_URL must be set at build time (Vite bakes env vars into bundle)
# Railway passes this via build args from environment variables
ARG VITE_API_URL=https://backend-production-507c.up.railway.app
ENV VITE_API_URL=$VITE_API_URL

# Cache buster - change this to force rebuild
ARG CACHE_BUST=30

# Build the app (VITE_API_URL is now available to Vite)
COPY . .
RUN echo "Cache bust: $CACHE_BUST - Building with VITE_API_URL=$VITE_API_URL" && npm run build

# Production stage - serve static files
FROM node:20-alpine

WORKDIR /app

# Install serve for static hosting
RUN npm install -g serve

# Copy built assets
COPY --from=builder /app/dist ./dist

# Railway provides PORT
ENV PORT=3000
EXPOSE $PORT

# Serve the built app
CMD ["sh", "-c", "serve -s dist -l $PORT"]
