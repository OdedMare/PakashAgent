import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "משמרות זהב — שיבוצים צבאיים",
  description: "מערכת להגדרה ולניהול ידני של שיבוצים צבאיים",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl">
      <body>
        <a className="skip-link" href="#main-content">
          דלגו לתוכן הראשי
        </a>
        {children}
      </body>
    </html>
  );
}
