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
  // Disable redirects for the webhook endpoint
  async redirects() {
    return [
      {
        source: '/api/telegram/webhook',
        destination: '/api/telegram/webhook',
        permanent: false,
        has: [
          {
            type: 'header',
            key: 'content-type',
            value: 'application/json',
          },
        ],
      },
    ]
  },
  // Add logging for debugging
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
}

module.exports = nextConfig 