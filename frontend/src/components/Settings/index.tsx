"use client";

import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  LockKeyhole,
  Save,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import { SettingsContent, SettingsNavigation } from "./SettingsSections";
import type { SettingsController } from "./useSettings";
import { useSettings } from "./useSettings";

/** The system settings inline, for the צוות משמרות זהב console (D28) —
 *  the only place they are reachable from; team screens no longer open them.
 *
 *  The operator's own session already passed the operator password, which
 *  the server accepts in place of the settings password — so this unlocks
 *  itself on mount with an empty header. Should that ever be refused, the
 *  ordinary unlock form is what renders, not a dead panel. */
export function SystemSettings() {
  const settings = useSettings();
  const { loaded, error, unlock } = settings;
  // A ref, not state: whether the one automatic attempt was made is not
  // something to render, and React's development double-mount must not send
  // it twice.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void unlock("");
  }, [unlock]);

  if (!loaded && !error) {
    return (
      <p className="settings-loading">
        <LoaderCircle className="spin" size={16} /> טוען הגדרות…
      </p>
    );
  }
  return <PanelContent settings={settings} />;
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
