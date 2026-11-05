import type { NextConfig } from "next";

// Static export: the build is plain HTML/JS/CSS served from S3 behind CloudFront.
// trailingSlash makes every page a folder with index.html (CloudFront rewrites /x/ -> /x/index.html).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};

export default nextConfig;
