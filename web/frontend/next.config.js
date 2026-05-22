/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    domains: ['localhost', 'magic-ai-factory.com'],
  },
  async rewrites() {
    const backend = process.env.AICOM_BACKEND_INTERNAL_URL || 'http://localhost:8081';
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
