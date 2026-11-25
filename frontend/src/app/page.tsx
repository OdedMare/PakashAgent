import { Workspace } from "@/components/Workspace";

export default async function Page({ searchParams }: {
  searchParams: Promise<{ view?: string }>;
}) {
  return <Workspace requests={(await searchParams).view === "constraints"} />;
}
