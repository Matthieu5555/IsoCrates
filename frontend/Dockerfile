FROM node:20-alpine

WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy application files
COPY . .

# Base path for production build
ARG NEXT_PUBLIC_BASE_PATH=/IsoCrates
ENV NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH

# Build the application
RUN npm run build

# Switch to non-root user
RUN chown -R nextjs:nodejs .next
USER nextjs

# Expose port
EXPOSE 3001

# Start the application
CMD ["npm", "start"]
