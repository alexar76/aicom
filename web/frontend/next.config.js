/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    domains: ['localhost', 'magic-ai-factory.com'],
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8081/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
