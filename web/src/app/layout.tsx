import type { Metadata } from "next";
import { Noto_Sans } from "next/font/google";
import "./globals.css";

// Noto Sans covers Mongolian Cyrillic (Ө, Ү) - also the PDF font (docs/06 §8).
const noto = Noto_Sans({ variable: "--font-noto", subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  title: "LabTrack MN",
  description: "Эрхтэн шилжүүлэн суулгуулсан хүмүүсийн эрүүл мэндийн мэдээлэл",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="mn" className={`${noto.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
