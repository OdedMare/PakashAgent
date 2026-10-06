import { MemberEntry } from "@/components/Workspace/MemberEntry";

/** The share link a member follows: `/team/<token>`.
 *
 *  The token is exchanged for a session cookie on arrival and then dropped
 *  from the address bar, so the rest of the visit does not carry the
 *  credential in a URL that lands in history and in screenshots. */
export default async function TeamPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <MemberEntry token={token} />;
}
