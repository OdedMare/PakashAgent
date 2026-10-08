"use client";

import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  LockKeyhole,
  Save,
  Settings2,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { SettingsContent, SettingsNavigation } from "./SettingsSections";
import type { SettingsController } from "./useSettings";
import { useSettings } from "./useSettings";
import { RotationSettings } from "./RotationSettings";
import type { WorkplaceProfile } from "@/types";

/**
 * The settings modal: model connection and database, saved live.
 *
 * Ported from AiSummryIO's SettingsPanel. Opens locked: these settings are
 * shared by every workspace on the server, so the boss login is not enough
 * and the panel asks for the settings password first. The backend checks it
 * on every call; this screen only collects it.
 */
export function SettingsPanel({ onClose, profile, onProfileSaved }: {
  onClose: () => void;
  profile?: WorkplaceProfile;
  onProfileSaved?: () => void | Promise<void>;
}) {
  const settings = useSettings();
  const [tab, setTab] = useState(profile ? "rotation" : "system");

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
    <div className="modal-backdrop settings-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal settings-workspace-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        // The backdrop closes on click; the dialog must not inherit that.
        onClick={(event) => event.stopPropagation()}
      >
        <ModalHeader onClose={onClose} />
        {profile ? <nav className="settings-top-tabs" aria-label="סוג ההגדרות">
          <button type="button" aria-current={tab === "rotation" ? "page" : undefined} onClick={() => setTab("rotation")}>סבבים ותלתונים</button>
          <button type="button" aria-current={tab === "system" ? "page" : undefined} onClick={() => setTab("system")}>הגדרות מערכת</button>
        </nav> : null}
        {profile ? <div className="rotation-settings-page" hidden={tab !== "rotation"}>
          <RotationSettings profile={profile} onSaved={onProfileSaved ?? (() => undefined)} />
        </div> : null}
        {tab === "system" ? <PanelContent settings={settings} /> : null}
      </section>
    </div>
  );
}

/** The system settings inline, for the צוות משמרות זהב console (D28).
 *
 *  The operator's own session already passed the operator password, which
 *  the server accepts in place of the settings password — so this unlocks
 *  itself on mount with an empty header. Should that ever be refused, the
 *  ordinary unlock form is what renders, not a dead panel. */
export function SystemSettings() {
  const settings = useSettings();
  const { loaded, loading, unlock } = settings;
  const [tried, setTried] = useState(false);

  useEffect(() => {
    if (tried || loaded || loading) return;
    setTried(true);
    void unlock("");
  }, [tried, loaded, loading, unlock]);

  if (!loaded && (!tried || loading)) {
    return (
      <p className="settings-loading">
        <LoaderCircle className="spin" size={16} /> טוען הגדרות…
      </p>
    );
  }
  return <PanelContent settings={settings} />;
}

function ModalHeader({ onClose }: { onClose: () => void }) {
  return (
    <header className="modal-header">
      <span className="modal-icon" aria-hidden="true">
        <Settings2 size={20} />
      </span>
      <div>
        <h2 id="settings-title">הגדרות</h2>
        <p>סבבים, נוכחות, מודל הבינה ומסד הנתונים.</p>
      </div>
      <button type="button" onClick={onClose} aria-label="סגירת הגדרות">
        <X size={18} />
      </button>
    </header>
  );
}

function PanelContent({ settings }: { settings: SettingsController }) {
  // Until a password has been accepted there are no values to edit, so a
  // load failure belongs on the unlock form. A *save* failure is different —
  // the values are still there, and the message belongs in the footer beside
  // the button that produced it.
  if (!settings.loaded) return <UnlockForm settings={settings} />;
  return <SettingsWorkspace settings={settings} />;
}

function UnlockForm({ settings }: { settings: SettingsController }) {
  const [password, setPassword] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (password) void settings.unlock(password);
  };
  return (
    <form className="settings-unlock" onSubmit={submit} autoComplete="off">
      <label className="field-label" htmlFor="settings-password">
        <LockKeyhole size={15} aria-hidden="true" /> סיסמת הגדרות המערכת
      </label>
      <input
        id="settings-password"
        className="settings-input"
        type="password"
        dir="ltr"
        autoFocus
        // Not the workspace password: keep password managers from offering it.
        autoComplete="new-password"
        data-1p-ignore="true"
        data-lpignore="true"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        disabled={settings.loading}
      />
      {settings.error ? (
        <p className="form-error" role="alert">
          <AlertTriangle size={16} /> {settings.error}
        </p>
      ) : null}
      <button
        className="primary-button"
        type="submit"
        disabled={!password || settings.loading}
      >
        {settings.loading ? (
          <><LoaderCircle className="spin" size={16} /> בודק…</>
        ) : (
          "פתיחה"
        )}
      </button>
    </form>
  );
}

function SettingsWorkspace({ settings }: { settings: SettingsController }) {
  return (
    <form
      className="settings-workspace"
      onSubmit={settings.save}
      autoComplete="off"
    >
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
