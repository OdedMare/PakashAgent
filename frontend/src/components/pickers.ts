/** Opens the browser's own picker for a native date/time input that is kept
 * out of sight. `showPicker` is the supported way; older browsers fall back to
 * focusing and clicking the input, which is what opens it there. */
export function openNativePicker(input: HTMLInputElement | null) {
  if (!input) return;
  try {
    if (typeof input.showPicker === "function") {
      input.showPicker();
      return;
    }
  } catch {
    // Refused (e.g. not a user gesture) -- fall through to the click.
  }
  input.focus();
  input.click();
}
