import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',
  // distDir: 'out', // This is the default directory for static export
  // images: {
  //   unoptimized: true, // Needed for `output: 'export'`
  // },
};

export default nextConfig;
