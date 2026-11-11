import type { Metadata } from "next";

import { AdminConsole } from "@/components/Admin";

export const metadata: Metadata = {
  title: "צוות משמרות זהב — מרכז שליטה",
};

export default function AdminPage() {
  return <AdminConsole />;
}
