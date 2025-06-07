/** @type {import('next').NextConfig} */
const nextConfig = {
  async headers() {
    return [
      {
        source: '/api/telegram/webhook',
        headers: [
          {
            key: 'Access-Control-Allow-Origin',
            value: '*',
          },
          {
            key: 'Access-Control-Allow-Methods',
            value: 'POST, OPTIONS',
          },
          {
            key: 'Access-Control-Allow-Headers',
            value: 'Content-Type',
          },
          {
            key: 'Cache-Control',
            value: 'no-store, no-cache, must-revalidate, proxy-revalidate',
          },
          {
            key: 'Pragma',
            value: 'no-cache',
          },
          {
            key: 'Expires',
            value: '0',
          },
        ],
      },
    ]
  },
  // Completely disable all redirects
  async redirects() {
    return []
  },
  // Completely disable all rewrites
  async rewrites() {
    return []
  },
  // Add logging for debugging
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
  // Ensure trailing slashes are handled correctly
  trailingSlash: false,
  // Disable automatic HTTPS redirect
  experimental: {
    skipTrailingSlashRedirect: true,
    skipMiddlewareUrlNormalize: true,
  },
}

module.exports = nextConfig 