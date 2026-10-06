import type { Metadata } from "next";
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
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Hebrew:wght@400;500;600;700&display=swap"
        />
      </head>
      <body>
        <a className="skip-link" href="#main-content">
          דלגו לתוכן הראשי
        </a>
        {children}
      </body>
    </html>
  );
}
