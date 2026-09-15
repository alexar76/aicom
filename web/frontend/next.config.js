const path = require('path');

const monorepoRoot = path.join(__dirname, '../..');

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: monorepoRoot,
  // /api/products can take 20–40s on cold scan; default Next proxy timeout is 30s.
  experimental: {
    proxyTimeout: 120_000,
  },
  turbopack: {
    root: monorepoRoot,
  },
  images: {
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost' },
      { protocol: 'https', hostname: 'magic-ai-factory.com' },
    ],
  },
  async rewrites() {
    const backend =
      process.env.AICOM_BACKEND_INTERNAL_URL ||
      process.env.INTERNAL_API_URL ||
      'http://localhost:8081';
    return [
      {
        source: '/api/:path*',
        destination: `${backend}/api/:path*`,
      },
      {
        source: '/.well-known/ai-market.json',
        destination: `${backend}/.well-known/ai-market.json`,
      },
      {
        source: '/ai-market/:path*',
        destination: `${backend}/ai-market/:path*`,
      },
      {
        source: '/capabilities/:path*',
        destination: `${backend}/capabilities/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
