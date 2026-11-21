import type { Metadata } from "next";
import { Public_Sans } from "next/font/google";
import "./globals.css";

// Design reference: docs/design/DESIGN_REFERENCE.md (Public Sans, tabular numbers).
const publicSans = Public_Sans({
  variable: "--font-public-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Replyline",
  description: "Turn incoming leads into organized business opportunities.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${publicSans.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
