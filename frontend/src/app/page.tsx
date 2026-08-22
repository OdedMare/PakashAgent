import { CircleHelp } from "lucide-react";
import Link from "next/link";

import { Workspace } from "@/components/Workspace";

export default function Page() {
  return (
    <>
      <Workspace />
      <Link className="tutorial-fab" href="/tutorial" aria-label="מדריך למערכת">
        <CircleHelp size={19} />
        <span>מדריך</span>
      </Link>
    </>
  );
}
