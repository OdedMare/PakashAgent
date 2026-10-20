import { PlugZap } from "lucide-react";

import type { RedisReport } from "@/types";

import { SettingsField as Field } from "./SettingsField";
import type { SettingsController } from "./useSettings";

/** The Redis connection, and what this deployment keeps in it.
 *
 *  Redis is optional: with the URL and host empty, the login throttle and the
 *  manager's live updates stay in each process's memory, and the model queue
 *  stays in PostgreSQL, as they always did. The card below the fields answers from the server, so a
 *  connection can be tested before it is saved. */
export function RedisSettings({ settings }: { settings: SettingsController }) {
  return (
    <section className="settings-section">
      <h3>Redis — מצב משותף בין תהליכים</h3>
      <Field
        settings={settings}
        name="redis_url"
        label="כתובת Redis"
        optional="ריק עם שרת ריק = ללא Redis; host:port מתקבל"
        placeholder="redis://localhost:6379/0"
      />
      <div className="settings-input-row">
        <div>
          <Field
            settings={settings}
            name="redis_host"
            label="שרת"
            optional="גובר על השרת שבכתובת; לבד מספיק"
            placeholder="localhost"
          />
        </div>
        <div>
          <Field
            settings={settings}
            name="redis_port"
            label="פורט"
            type="number"
            min="1"
            max="65535"
            optional="ריק = 6379"
            placeholder="6379"
          />
        </div>
      </div>
      <div className="settings-input-row">
        <div>
          <Field
            settings={settings}
            name="redis_username"
            label="שם משתמש"
            optional="ריק = default"
            placeholder="default"
          />
        </div>
        <div>
          <Field
            settings={settings}
            name="redis_password"
            label="סיסמה"
            type="password"
            optional="אם השרת דורש"
            placeholder="סיסמה"
          />
        </div>
      </div>
      <Field
        settings={settings}
        name="redis_key_prefix"
        label="קידומת מפתחות"
        optional="להפרדה בין התקנות על אותו Redis"
        placeholder="pakash"
      />
      <div className="model-field-header">
        <span className="field-label">מצב החיבור</span>
        <button
          type="button"
          className="models-refresh"
          onClick={() => void settings.testRedis()}
          disabled={settings.redisTesting}
        >
          <PlugZap size={14} />
          {settings.redisTesting ? "בודק…" : "בדיקת חיבור"}
        </button>
      </div>
      {settings.redisError ? (
        <p className="models-status error" role="alert">{settings.redisError}</p>
      ) : null}
      <RedisReportCard report={settings.redisReport} />
      <p className="settings-note">
        עם Redis שלושה דברים משותפים לכל תהליכי השרת: נעילת חשבון אחרי סיסמאות שגויות, עדכון
        מיידי של מסך המנהל כשעובד שולח בקשה, ותור הפניות למודל — לפי סדר עדיפות, כך ששיחה עם
        המנהל עוקפת בניית סידור שממתינה, וכל צוות מריץ פנייה אחת בכל רגע. כש-Redis לא זמין,
        הנעילה והעדכונים חוזרים לזיכרון של כל תהליך, והתור חוזר למסד הנתונים. שינוי נקלט בכל
        התהליכים תוך שניות, בלי הפעלה מחדש.
      </p>
    </section>
  );
}

function RedisReportCard({ report }: { report: RedisReport | null }) {
  if (!report) return null;
  if (!report.configured) {
    return <p className="models-status">Redis לא מוגדר — הכול עובד בזיכרון של כל תהליך.</p>;
  }
  if (!report.connected) {
    return (
      <p className="models-status error" role="alert" dir="auto">
        אין חיבור ל-{report.url}: {report.error}
      </p>
    );
  }
  const { server, app, live } = report;
  const rows: [string, string | number][] = [
    ["גרסה", `${server?.version ?? ""}${server?.mode ? ` (${server.mode})` : ""}`],
    ["זמן תגובה", `${server?.latency_ms ?? 0} ms`],
    ["זמן פעילות", formatUptime(server?.uptime_seconds ?? 0)],
    ["זיכרון בשימוש", server?.used_memory ?? ""],
    ["לקוחות מחוברים", server?.connected_clients ?? 0],
    ["מפתחות במסד", server?.keys ?? 0],
    ["מפתחות של המערכת", app?.keys ?? 0],
    ["פניות פעילות למודל", app?.model_calls ?? 0],
    ["ממתינים בתור למודל", app?.model_waiting ?? 0],
    ["חשבונות נעולים", app?.locked_accounts ?? 0],
    ["מאזיני עדכונים חיים", app?.event_listeners ?? 0],
  ];
  return (
    <div className="redis-report">
      <p className="models-status">
        מחובר ל-<span dir="ltr">{report.url}</span>
        {live ? (live.connected ? " · השרת משתמש בו עכשיו" : " · השרת עדיין לא משתמש בו (שמרו את ההגדרות)") : null}
      </p>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd dir="ltr">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function formatUptime(seconds: number) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days} ימים, ${hours} שעות`;
  if (hours) return `${hours} שעות, ${minutes} דקות`;
  return `${minutes} דקות`;
}
