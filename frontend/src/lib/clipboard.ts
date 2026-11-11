/** Copy text to the clipboard, and say whether it worked.
 *
 *  `navigator.clipboard` exists only in a secure context. The team opens this
 *  app at a plain-HTTP LAN address (http://10.0.0.x:3000), where the API is
 *  simply absent — so every "copy" button silently did nothing there. The
 *  fallback is the older selection-based `execCommand("copy")`, which still
 *  works over HTTP as long as it runs inside the click that asked for it. */
export async function copyText(text: string): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission refused or document not focused — try the fallback.
    }
  }
  return copyBySelection(text);
}

function copyBySelection(text: string): boolean {
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  // Off-screen but still selectable; `display: none` cannot be selected.
  field.style.position = "fixed";
  field.style.top = "0";
  field.style.left = "-9999px";
  field.style.opacity = "0";
  const focused = document.activeElement as HTMLElement | null;
  document.body.appendChild(field);
  field.select();
  field.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  field.remove();
  focused?.focus({ preventScroll: true });
  return ok;
}
