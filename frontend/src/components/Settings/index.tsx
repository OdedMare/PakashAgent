"use client";

import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  Save,
  Settings2,
  X,
} from "lucide-react";
import { useEffect } from "react";

import { SettingsContent, SettingsNavigation } from "./SettingsSections";
import type { SettingsController } from "./useSettings";
import { useSettings } from "./useSettings";

/**
 * The settings modal: model connection and database, saved live.
 *
 * Ported from AiSummryIO's SettingsPanel. There is no authorization gate here
 * — PakashAgent is single-tenant and local, so the backend exposes these
 * routes unguarded and there is nothing for the panel to check.
 */
export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const settings = useSettings();

  // Escape closes, as a modal should. Bound on the document rather than the
  // dialog so it works before anything inside has taken focus.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal settings-workspace-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        // The backdrop closes on click; the dialog must not inherit that.
        onClick={(event) => event.stopPropagation()}
      >
        <ModalHeader onClose={onClose} />
        <PanelContent settings={settings} />
      </section>
    </div>
  );
}

function ModalHeader({ onClose }: { onClose: () => void }) {
  return (
    <header className="modal-header">
      <span className="modal-icon" aria-hidden="true">
        <Settings2 size={20} />
      </span>
      <div>
        <h2 id="settings-title">הגדרות מערכת</h2>
        <p>ניהול מודל הבינה ומסד הנתונים.</p>
      </div>
      <button type="button" onClick={onClose} aria-label="סגירת הגדרות">
        <X size={18} />
      </button>
    </header>
  );
}

function PanelContent({ settings }: { settings: SettingsController }) {
  if (settings.loading) {
    return (
      <p className="loading-line">
        <LoaderCircle className="spin" size={16} /> טוען…
      </p>
    );
  }
  // A load failure leaves no values to edit, so the form is not worth showing.
  // A *save* failure is different — the values are still there, and the
  // message belongs in the footer beside the button that produced it.
  if (!settings.loaded) {
    return (
      <p className="form-error" role="alert">
        <AlertTriangle size={18} /> {settings.error}
      </p>
    );
  }
  return <SettingsWorkspace settings={settings} />;
}

function SettingsWorkspace({ settings }: { settings: SettingsController }) {
  return (
    <form className="settings-workspace" onSubmit={settings.save}>
      <div className="settings-workspace-layout">
        <SettingsNavigation
          active={settings.activeSection}
          onChange={settings.setActiveSection}
        />
        <SettingsContent settings={settings} />
      </div>
      <SettingsFooter settings={settings} />
    </form>
  );
}

function SettingsFooter({ settings }: { settings: SettingsController }) {
  return (
    <footer className="settings-footer">
      {settings.error ? (
        <span className="settings-message form-error" role="alert">
          <AlertTriangle size={16} /> {settings.error}
        </span>
      ) : null}
      {!settings.error && settings.message ? (
        <span className="settings-message form-success" role="status">
          <CheckCircle2 size={16} /> {settings.message}
        </span>
      ) : null}
      <button
        className="primary-button settings-save"
        type="submit"
        disabled={settings.saving}
      >
        <Save size={17} /> {settings.saving ? "שומר…" : "שמירת שינויים"}
      </button>
    </footer>
  );
}
