import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "פקש — ראיון היכרות",
  description: "סוכן שבונה ומתחזק סידורי משמרות בשיחה",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl">
      <body>
        <a className="skip-link" href="#interview">
          דלגו לראיון
        </a>
        {children}
      </body>
    </html>
  );
}
