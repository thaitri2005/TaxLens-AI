import type { Metadata, Viewport } from "next";
import { Be_Vietnam_Pro, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import Providers from "./providers";

// Both families carry a Vietnamese subset, so English and Vietnamese share one typeface (no
// fallback to Arial for diacritics). next/font self-hosts them: no request to Google at runtime.
const sans = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-sans",
});
const serif = Source_Serif_4({
  subsets: ["latin", "vietnamese"],
  display: "swap",
  variable: "--font-serif",
});

export const metadata: Metadata = {
  title: "TaxLens AI",
  description: "Evidence-grounded Vietnamese tax regulation intelligence",
};

export const viewport: Viewport = {
  themeColor: "#f7f8f5",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
