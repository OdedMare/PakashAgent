import type { Metadata } from "next";
import { GuideProvider } from "@/components/Guide";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "פקש — שיבוצים צבאיים",
  description: "מערכת להגדרה ולניהול ידני של שיבוצים צבאיים",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl">
      <head>
        {/* A plain <link> rather than next/font: next/font fetches at build
            time, and an image built without network would fail outright,
            where this just falls back to system faces. The lint rule below
            targets pages/_document and misfires on an App Router root layout,
            which already wraps every page. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Hebrew:wght@400;500;600;700&display=swap"
        />
      </head>
      <body>
        <a className="skip-link" href="#main-content">
          דלגו לתוכן הראשי
        </a>
        {/* The help button and guided tour sit above every page, so each
            screen only says which surface it is rather than mounting its own. */}
        <GuideProvider>{children}</GuideProvider>
      </body>
    </html>
  );
}
