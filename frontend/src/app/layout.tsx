import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LEESA · Doc Weather Social Media Liaison",
  description:
    "LEESA helps Doc Weather manage videos and writing across X, Instagram, TikTok, and YouTube.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
