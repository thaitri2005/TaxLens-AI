import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TaxLens AI",
  description: "Evidence-grounded Vietnamese tax regulation intelligence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
