"use client";

import { FormEvent, useEffect, useState } from "react";

import { getSettings, probeModels, updateSettings } from "@/services/api";

export type SettingsSection = "agent" | "schedule" | "database";

/** What the backend returns in place of a stored secret, and what it accepts
 *  back to mean "unchanged". Must match `MASKED_SECRET` in
 *  `backend/app/common/runtime_settings/normalizers.py`. */
const MASKED = "********";

/**
 * All settings-panel state in one place: the loaded values, the edits made on
 * top of them, and the model list.
 *
 * Values are held as a loose `Record` rather than a typed object because the
 * fields are declared once in `SettingsSections` by name — keeping a second
 * typed copy here would mean editing two places to add a field, and the
 * backend is the real validator either way.
 */
export function useSettings() {
  const [activeSection, setActiveSection] = useState<SettingsSection>("agent");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // Model lists are per connection, not global: with roles free to sit on
  // different providers, one shared list would offer the general server's
  // catalogue for a field served by another. Keyed by role name, with ""
  // for the general connection.
  const [modelsByRole, setModelsByRole] = useState<Record<string, string[]>>({});
  // `null`, not "": the general connection *is* the empty role name, so an
  // empty string could not tell "nothing is loading" from "the general one
  // is" — and the general refresh button would never show its spinner.
  const [loadingRole, setLoadingRole] = useState<string | null>(null);
  const [errorsByRole, setErrorsByRole] = useState<Record<string, string>>({});

  useEffect(() => {
    getSettings()
      .then((next) => {
        setValues(next as unknown as Record<string, unknown>);
        setLoaded(true);
        // Fill the model datalist from the saved connection right away. A
        // failure here is not worth showing before the boss asks for it —
        // the model server simply may not be running yet.
        void probeModels({ llm_base_url: String(next.llm_base_url ?? "") })
          .then((result) => setModelsByRole((current) => ({
            ...current, "": result.models,
          })))
          .catch(() => undefined);
      })
      .catch((reason) => setError(errorMessage(reason, "טעינת ההגדרות נכשלה")))
      .finally(() => setLoading(false));
  }, []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await updateSettings(values);
      setValues(saved as unknown as Record<string, unknown>);
      setMessage("ההגדרות נשמרו ויחולו על הפנייה הבאה.");
    } catch (reason) {
      setError(errorMessage(reason, "השמירה נכשלה"));
    } finally {
      setSaving(false);
    }
  };

  /** Probe one connection. `role` is "" for the general one, or a role name
   *  whose own URL and key are sent when the form carries them.
   *
   *  The URL and key are read from the form fields belonging to that role, so
   *  an endpoint can be tested before it is saved — and an empty role field
   *  is sent empty rather than filled in from the general one, because the
   *  backend already applies exactly that fallback and doing it here too
   *  would hide which connection actually answered. */
  const loadModels = async (role = "") => {
    setLoadingRole(role);
    setErrorsByRole((current) => ({ ...current, [role]: "" }));
    try {
      // What is typed in the form wins, so a base URL or key can be tested
      // before it is saved. An untouched secret is still masked, and the
      // backend reads that as "use the stored one".
      const urlKey = role ? `llm_base_url_${role}` : "llm_base_url";
      const secretKey = role ? `llm_api_key_${role}` : "openai_api_key";
      const result = await probeModels({
        llm_base_url: String(values[urlKey] ?? ""),
        openai_api_key: String(values[secretKey] ?? ""),
        role,
      });
      setModelsByRole((current) => ({ ...current, [role]: result.models }));
    } catch (reason) {
      setErrorsByRole((current) => ({
        ...current,
        [role]: errorMessage(reason, "טעינת המודלים נכשלה"),
      }));
    } finally {
      setLoadingRole(null);
    }
  };

  const set = (key: string, value: unknown) =>
    setValues((current) => ({ ...current, [key]: value }));
  const text = (key: string) => String(values[key] ?? "");
  const checked = (key: string) => Boolean(values[key]);
  /** True when a secret is stored but not being retyped, so the field shows
   *  "(נשמר)" and stays empty instead of rendering the mask as content. */
  const secretSaved = (key: string) => values[key] === MASKED;

  /** What a role's field should offer: its own probe when it has one,
   *  otherwise the general list — which mirrors the backend's own fallback,
   *  so a role with no URL of its own is served by the endpoint that will
   *  actually answer for it. */
  const modelsFor = (role = "") => modelsByRole[role] ?? modelsByRole[""] ?? [];
  const modelsErrorFor = (role = "") => errorsByRole[role] ?? "";

  return {
    activeSection, setActiveSection, loaded, loading, saving, message, error,
    modelsFor, modelsErrorFor, loadingRole,
    save, loadModels, set, text, checked, secretSaved,
  };
}

export type SettingsController = ReturnType<typeof useSettings>;

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}
