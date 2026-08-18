import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LEESA · Doc Weather Social Media Liaison",
  description:
    "LEESA helps Doc Weather manage videos and writing across X, Instagram, TikTok, and YouTube.",
  other: {
    // TikTok Developer Portal website verification (meta tag method)
    "tiktok-developers-site-verification": "IcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <meta
          name="tiktok-developers-site-verification"
          content="IcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
