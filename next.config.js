/** @type {import('next').NextConfig} */
// Static export (SPEC_WEB 4.1): no server functions, can be hosted on any static host.
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

module.exports = nextConfig;
