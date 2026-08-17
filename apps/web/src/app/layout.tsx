import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ACE Mandate Assurance",
  description: "Authenticate the agent. Verify the outcome.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

