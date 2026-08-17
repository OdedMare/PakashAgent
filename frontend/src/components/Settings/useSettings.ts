"use client";

import { FormEvent, useEffect, useState } from "react";

import { getSettings, probeModels, updateSettings } from "@/services/api";

export type SettingsSection = "agent" | "database";

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
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsError, setModelsError] = useState("");

  useEffect(() => {
    getSettings()
      .then((next) => {
        setValues(next as unknown as Record<string, unknown>);
        setLoaded(true);
        // Fill the model datalist from the saved connection right away. A
        // failure here is not worth showing before the boss asks for it —
        // the model server simply may not be running yet.
        void probeModels({ llm_base_url: String(next.llm_base_url ?? "") })
          .then((result) => setModels(result.models))
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

  const loadModels = async () => {
    setLoadingModels(true);
    setModelsError("");
    try {
      // What is typed in the form wins, so a base URL or key can be tested
      // before it is saved. An untouched secret is still masked, and the
      // backend reads that as "use the stored one".
      const result = await probeModels({
        llm_base_url: String(values.llm_base_url ?? ""),
        openai_api_key: String(values.openai_api_key ?? ""),
      });
      setModels(result.models);
    } catch (reason) {
      setModelsError(errorMessage(reason, "טעינת המודלים נכשלה"));
    } finally {
      setLoadingModels(false);
    }
  };

  const set = (key: string, value: unknown) =>
    setValues((current) => ({ ...current, [key]: value }));
  const text = (key: string) => String(values[key] ?? "");
  const checked = (key: string) => Boolean(values[key]);
  /** True when a secret is stored but not being retyped, so the field shows
   *  "(נשמר)" and stays empty instead of rendering the mask as content. */
  const secretSaved = (key: string) => values[key] === MASKED;

  return {
    activeSection, setActiveSection, loaded, loading, saving, message, error,
    models, loadingModels, modelsError,
    save, loadModels, set, text, checked, secretSaved,
  };
}

export type SettingsController = ReturnType<typeof useSettings>;

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}
