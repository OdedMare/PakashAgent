import { AlertTriangle, CheckCircle2, LoaderCircle } from "lucide-react";

import type { LibraryController } from "./useLibrary";

/** The result of the last library write, under the editor that made it. */
export function LibraryStatus({ state }: { state: LibraryController }) {
  if (state.error) {
    return (
      <p className="library-status form-error" role="alert">
        <AlertTriangle size={16} aria-hidden="true" /> {state.error}
      </p>
    );
  }
  if (state.message) {
    return (
      <p className="library-status form-success" role="status">
        <CheckCircle2 size={16} aria-hidden="true" /> {state.message}
      </p>
    );
  }
  return null;
}

export function LibraryLoading() {
  return (
    <p className="settings-loading">
      <LoaderCircle className="spin" size={16} /> טוען…
    </p>
  );
}
