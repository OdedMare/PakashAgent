import type { Metadata } from "next";
import { GuideProvider } from "@/components/Guide";
import "@/styles/globals.css";

const themeScript = `
(() => {
  const systemTheme = () => matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  try {
    const stored = localStorage.getItem("pakash.theme");
    document.documentElement.dataset.theme = stored === "light" || stored === "dark" ? stored : systemTheme();
  } catch {
    document.documentElement.dataset.theme = systemTheme();
  }
})();`;

export const metadata: Metadata = {
  title: "משמרות זהב — שיבוצים צבאיים",
  description: "מערכת להגדרה ולניהול ידני של שיבוצים צבאיים",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
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
