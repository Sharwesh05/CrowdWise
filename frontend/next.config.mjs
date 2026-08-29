/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**" },
      { protocol: "http", hostname: "localhost" },
    ],
  },
  async rewrites() {
    // Not used by default (the client calls the API origin directly with
    // credentials), but available when the API is proxied behind the same host.
    return [];
  },
};

export default nextConfig;
