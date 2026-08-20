import { Bot, Database, RefreshCw } from "lucide-react";

import { SettingsField as Field, SettingsToggle as Toggle } from "./SettingsField";
import type { SettingsController, SettingsSection } from "./useSettings";

/** The category rail. Each id matches a key in `SettingsContent` below, so
 *  adding a section means adding it in both places and nowhere else. */
const SECTIONS = [
  {
    id: "agent" as const,
    label: "סוכן ומודל",
    description: "מודל, כתובת בסיס ומפתח API",
    icon: Bot,
  },
  {
    id: "database" as const,
    label: "מסד הנתונים",
    description: "חיבור PostgreSQL וסכמה",
    icon: Database,
  },
];

export function SettingsNavigation({
  active,
  onChange,
}: {
  active: SettingsSection;
  onChange: (section: SettingsSection) => void;
}) {
  return (
    <nav className="settings-nav" aria-label="קטגוריות הגדרות">
      <p className="settings-nav-label">קטגוריות</p>
      {SECTIONS.map(({ id, label, description, icon: Icon }) => (
        <button
          key={id}
          type="button"
          className={active === id ? "active" : ""}
          onClick={() => onChange(id)}
          aria-current={active === id ? "page" : undefined}
        >
          <Icon size={18} />
          <span>
            <strong>{label}</strong>
            <small>{description}</small>
          </span>
        </button>
      ))}
    </nav>
  );
}

export function SettingsContent({ settings }: { settings: SettingsController }) {
  const sections = {
    agent: <AgentSettings settings={settings} />,
    database: <DatabaseSettings settings={settings} />,
  };
  return <div className="settings-content">{sections[settings.activeSection]}</div>;
}

function AgentSettings({ settings }: { settings: SettingsController }) {
  return (
    <section className="settings-section">
      <h3>מודל בינה מלאכותית</h3>
      <Field
        settings={settings}
        name="openai_api_key"
        label="מפתח API"
        type="password"
        optional="לא נדרש לשרתים מקומיים כמו Ollama"
        placeholder="sk-…"
      />
      <ModelField settings={settings} />
      <Field
        settings={settings}
        name="llm_base_url"
        label="כתובת בסיס"
        type="url"
        optional="שרת תואם OpenAI; ריק = OpenAI"
        placeholder="http://localhost:11434/v1"
      />
      <Toggle
        settings={settings}
        name="llm_diet_mode"
        label="מצב חסכוני בטוקנים"
        optional="הנחיות קצרות ופלט מוגבל"
      />
      <Field
        settings={settings}
        name="llm_repetition_penalty"
        label="קנס חזרתיות"
        type="number"
        min="0"
        max="2"
        step="0.05"
        optional="0 מכבה; נתמך בשרתים מקומיים בלבד (לא ב-OpenAI)"
        placeholder="0"
      />
      <Field
        settings={settings}
        name="llm_timeout_seconds"
        label="זמן מרבי לתשובת המודל"
        type="number"
        min="1"
        optional="שניות"
        placeholder="120"
      />
    </section>
  );
}

/** The roles a task can be routed to. Mirrors `_FLOW_ROLES` in
 *  `backend/app/dal/llm/model_roles.py` — the backend does the routing, this
 *  only says which model each role uses.
 *
 *  No model name appears here, or anywhere else in the panel: which models
 *  exist is the server's answer, read from `/v1/models`. */
const MODEL_ROLES = [
  {
    name: "llm_model_fast",
    label: "מודל מהיר",
    optional: "משימות קצרות — תדריך יומי",
  },
  {
    name: "llm_model_default",
    label: "מודל ברירת מחדל",
    optional: "ראיון, שיחה, הצעות שינוי ולמידה",
  },
  {
    name: "llm_model_advanced",
    label: "מודל מתקדם",
    optional: "בניית סידור וחשיבה מורכבת",
  },
];

/** The model fields carry one shared refresh button, so a base URL typed
 *  above can be probed without saving it first. */
function ModelField({ settings }: { settings: SettingsController }) {
  return (
    <>
      <div className="model-field-header">
        <label className="field-label" htmlFor="set-llm_model">
          מודל ברירת מחדל כללי
        </label>
        <button
          type="button"
          className="models-refresh"
          onClick={() => void settings.loadModels()}
          disabled={settings.loadingModels}
        >
          <RefreshCw className={settings.loadingModels ? "spin" : ""} size={14} />
          {settings.loadingModels ? "טוען…" : "רענון מודלים"}
        </button>
      </div>
      <ModelInput settings={settings} name="llm_model" />
      <p className="field-optional">
        המודל שישמש לכל תפקיד שלא הוגדר לו מודל משלו
      </p>
      {/* A datalist, not a select: a model the server does not list is still
          a legitimate thing to type. Shared by every model field — they all
          address the same endpoint, so they all offer the same ids. */}
      <datalist id="available-models">
        {settings.models.map((model) => (
          <option key={model} value={model} />
        ))}
      </datalist>
      <ModelStatus settings={settings} />
      {MODEL_ROLES.map((role) => (
        <div key={role.name} className="settings-role-field">
          <label className="field-label" htmlFor={`set-${role.name}`}>
            {role.label}
          </label>
          <ModelInput settings={settings} name={role.name} />
          <p className="field-optional">
            {role.optional} — ריק: שימוש במודל ברירת המחדל
          </p>
        </div>
      ))}
    </>
  );
}

/** One model input. Empty is meaningful — it is how a role is left unset —
 *  so there is no placeholder naming a model to fall back on. */
function ModelInput({
  settings,
  name,
}: {
  settings: SettingsController;
  name: string;
}) {
  return (
    <input
      id={`set-${name}`}
      className="settings-input"
      dir="ltr"
      list="available-models"
      value={settings.text(name)}
      onChange={(event) => settings.set(name, event.target.value)}
    />
  );
}

function ModelStatus({ settings }: { settings: SettingsController }) {
  if (settings.modelsError) {
    return (
      <p className="models-status error" role="alert" dir="auto">
        {settings.modelsError}
      </p>
    );
  }
  if (!settings.models.length) return null;
  return <p className="models-status">נמצאו {settings.models.length} מודלים זמינים</p>;
}

function DatabaseSettings({ settings }: { settings: SettingsController }) {
  return (
    <section className="settings-section">
      <h3>מסד הנתונים (PostgreSQL)</h3>
      <Field
        settings={settings}
        name="database_url"
        label="כתובת חיבור מלאה"
        optional="ברירת מחדל לשדות הריקים; כתובת jdbc מתקבלת ומומרת"
        placeholder="postgresql://localhost:5432/pakash"
      />
      <div className="settings-input-row">
        <div>
          <Field
            settings={settings}
            name="database_host"
            label="שרת"
            placeholder="localhost"
          />
        </div>
        <div>
          <Field
            settings={settings}
            name="database_port"
            label="פורט"
            type="number"
            min="1"
            max="65535"
            placeholder="5432"
          />
        </div>
      </div>
      <Field
        settings={settings}
        name="database_name"
        label="שם מסד הנתונים"
        placeholder="pakash"
      />
      <div className="settings-input-row">
        <div>
          <Field
            settings={settings}
            name="database_user"
            label="שם משתמש"
            placeholder="pakash"
          />
        </div>
        <div>
          <Field
            settings={settings}
            name="database_password"
            label="סיסמה"
            type="password"
            placeholder="סיסמה"
          />
        </div>
      </div>
      <Field
        settings={settings}
        name="database_schema"
        label="סכמה"
        optional="אותיות, ספרות וקו תחתון בלבד"
        placeholder="pakash"
      />
    </section>
  );
}
