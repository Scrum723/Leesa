/** @type {import('next').NextConfig} */
const repo = "Leesa";
const isGithubActions = process.env.GITHUB_ACTIONS === "true";

const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  // GitHub Pages serves at https://<user>.github.io/<repo>/
  basePath: isGithubActions ? `/${repo}` : "",
  assetPrefix: isGithubActions ? `/${repo}/` : undefined,
};

export default nextConfig;
