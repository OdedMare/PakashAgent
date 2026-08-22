import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowLeft,
  BarChart3,
  Bot,
  CalendarCheck,
  Check,
  FileDown,
  HelpCircle,
  MessageSquareText,
  MousePointer2,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
  Users,
} from "lucide-react";

export const metadata: Metadata = {
  title: "מדריך פקש — כל המערכת, צעד אחר צעד",
  description: "מדריך מצולם למנהלים ולעובדים במערכת פקש",
};

export default function TutorialPage() {
  return (
    <main id="main-content" className="tutorial-page">
      <header className="tutorial-topbar">
        <Link href="/" className="tutorial-brand" aria-label="חזרה לפקש">
          <span className="tutorial-brand-mark"><CalendarCheck size={17} /></span>
          <span><strong>פקש</strong><small>מדריך שימוש</small></span>
        </Link>
        <Link href="/" className="tutorial-back">למערכת <ArrowLeft size={15} /></Link>
      </header>

      <section className="tutorial-hero" aria-labelledby="tutorial-title">
        <div className="tutorial-hero-copy">
          <span className="tutorial-kicker"><Sparkles size={14} /> מהכניסה ועד לפרסום</span>
          <h1 id="tutorial-title">לא צריך לזכור<br />איפה כל דבר נמצא.</h1>
          <p>
            בחרו את התפקיד שלכם וקבלו מסלול קצר, מצולם ומדויק. כל פעולה במערכת
            נשארת באותו שם לאורך כל הדרך — מהכפתור ועד לאישור.
          </p>
          <nav className="tutorial-role-links" aria-label="בחירת מסלול במדריך">
            <a href="#manager"><ShieldCheck size={17} /> אני מנהל/ת</a>
            <a href="#employee"><UserRound size={17} /> אני עובד/ת</a>
            <a href="#team-view"><Users size={17} /> רק לצפות בלוח</a>
          </nav>
        </div>

        <div className="tutorial-route-map" aria-label="מסלול העבודה במערכת">
          <span className="route-time">07:00</span>
          <div className="route-stop is-active"><b>כניסה</b><small>הצוות והזהות שלכם</small></div>
          <span className="route-time">15:00</span>
          <div className="route-stop"><b>בנייה ובדיקה</b><small>סידור, שיחה ואזהרות</small></div>
          <span className="route-time">23:00</span>
          <div className="route-stop"><b>פרסום וטיפול</b><small>הצוות רואה ומגיש בקשות</small></div>
        </div>
      </section>

      <section className="tutorial-orientation" aria-labelledby="start-title">
        <div className="tutorial-section-heading">
          <span>נקודת פתיחה</span>
          <h2 id="start-title">נכנסים למרחב הנכון</h2>
          <p>למנהל יש סיסמה. לצוות יש קישור. לעובד יש זהות אישית בתוך הצוות.</p>
        </div>
        <Screenshot
          src="/tutorial/login.png"
          alt="מסך הכניסה לפקש, עם בחירת צוות ושדה סיסמה"
          caption="כניסת מנהל"
          note="בכניסה הראשונה בוחרים ‘פתיחת צוות חדש’. אחר כך הצוות נשמר ברשימה."
          callouts={[{ n: 1, label: "בחרו צוות", x: "20%", y: "32%" }, { n: 2, label: "הזינו סיסמה", x: "18%", y: "45%" }]}
        />
        <div className="tutorial-first-steps">
          <article><span>1</span><h3>פותחים צוות</h3><p>שם וסיסמה יוצרים סביבת עבודה נפרדת. שום לוח או כלל לא עוברים בין צוותים.</p></article>
          <article><span>2</span><h3>מלמדים את פקש</h3><p>ראיון קצר אוסף עובדים, שמות משמרות, צרכים וכללים. אפשר לעצור ולחזור אליו.</p></article>
          <article><span>3</span><h3>בוחרים איך להתחיל</h3><p>בונים סידור עם הסוכן, פותחים שבוע ריק לשיבוץ ידני, או מייבאים קובץ קיים.</p></article>
        </div>
      </section>

      <section id="manager" className="tutorial-path tutorial-manager" aria-labelledby="manager-title">
        <aside className="tutorial-rail" aria-hidden="true"><span>מנהל/ת</span></aside>
        <div className="tutorial-section-heading">
          <span>מסלול מנהל/ת</span>
          <h2 id="manager-title">מכינים שבוע, בודקים, ורק אז מפרסמים</h2>
          <p>הלוח הוא מרכז העבודה. כל כלי אחר נפתח לידו, כדי שלא תאבדו את ההקשר.</p>
        </div>

        <TutorialChapter number="01" title="לקרוא את הלוח" icon={<CalendarCheck size={19} />}>
          <p>מסילת השבוע מציגה מיד מה מוכן ומה דורש טיפול. הכרטיסים מסכמים איוש, חוסרים, התנגשויות ושעות; לחיצה על התנגשות מסננת את הלוח למקומות הרלוונטיים.</p>
          <Screenshot
            src="/tutorial/manager-board.png"
            alt="לוח המשמרות של המנהל עם מסילת שבוע, מדדי איוש ורשת משמרות"
            caption="לוח המשמרות"
            note="ירוק אומר מוכן; ענבר מצביע על נקודה שכדאי לבדוק. אזהרה אינה חוסמת פרסום."
            callouts={[{ n: 1, label: "עוברים שבוע", x: "53%", y: "8%" }, { n: 2, label: "מצב השבוע", x: "47%", y: "21%" }, { n: 3, label: "מסננים", x: "45%", y: "35%" }]}
          />
          <FeatureGrid items={[
            ["בנייה", "‘בניית הסידור’ מפעילה את הסוכן; ‘שבוע ריק’ משאיר את השליטה בידיים שלכם."],
            ["שיבוץ ידני", "לחצו על + בתא ריק ובחרו עובד. הסרה נעשית מכרטיס השיבוץ."],
            ["העברה", "גררו שיבוץ. המערכת תציג השפעה ותבקש סיבה לפני שהשינוי נשמר."],
            ["סינון", "סננו לפי עובד, תפקיד, משמרת, חוסרים או התנגשויות."],
            ["תקופות", "החצים עוברים בין שבועות; בורר התקופות מחזיר לכל סידור קודם."],
            ["פרסום", "‘פרסום לצוות’ הוא הרגע שבו העובדים מקבלים את הגרסה הנוכחית."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="02" title="לדבר עם הסוכן — בלי לתת לו לכתוב לבד" icon={<Bot size={19} />}>
          <p>פתחו ‘ניהול’ או ‘הסוכן’. זכוכית המגדלת שואלת שאלה לקריאה בלבד; כפתור השליחה מבקש שינוי. הצעה, סימולציה או גרירה תמיד מחכות לאישור ולסיבה.</p>
          <Screenshot
            src="/tutorial/manager-agent.png"
            alt="לוח המנהל לצד מגירת הסוכן, עם שאלות מהירות והרשאות"
            caption="מרחב הניהול והסוכן"
            note="הסוכן יכול להצביע על בעיה ולהציע ניסוח, אבל אינו מבצע שינוי מתוך התדריך."
            callouts={[{ n: 1, label: "כלי ניהול", x: "18%", y: "14%" }, { n: 2, label: "שואלים או משנים", x: "18%", y: "37%" }, { n: 3, label: "הרשאות", x: "18%", y: "72%" }]}
          />
          <div className="tutorial-two-column">
            <div><MessageSquareText size={18} /><h3>כשאתם שואלים</h3><p>תקבלו תשובה עם הבדיקות שעליהן היא נשענת. אין כפתור אישור, כי דבר לא השתנה.</p></div>
            <div><MousePointer2 size={18} /><h3>כשאתם מבקשים שינוי</h3><p>תראו את נימוק הסוכן ואת האזהרות הצפויות. הזינו סיבה ואשרו רק אם התוצאה מתאימה.</p></div>
          </div>
          <FeatureGrid items={[
            ["תדריך", "הסוכן מסכם מיוזמתו בכניסה, אחרי שינוי ולפני פרסום."],
            ["סימולציה", "‘מה יקרה אם…’ מחשב השפעה בלי לשמור דבר."],
            ["בקשות", "אישור או דחייה של אילוצי עובדים; דחייה דורשת סיבה."],
            ["החלפות", "החלפה ששני העובדים אישרו מגיעה להכרעת המנהל."],
            ["צוות", "ניהול עובדים, אילוצים וזהויות אישיות שנתפסו."],
            ["סקירה", "היסטוריה, העדפות שהסוכן למד, תיבת copilot ויומן ביקורת."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="03" title="לבדוק את התמונה הרחבה" icon={<BarChart3 size={19} />}>
          <p>מסך ‘נתונים’ מתרגם את אותו לוח לכיסוי, שעות, עומס לפי יום ולפי עובד, התפלגות משמרות ואזהרות. המספרים מסבירים את הלוח — הם לא נותנים לו ציון.</p>
          <Screenshot
            src="/tutorial/manager-analytics.png"
            alt="מסך הנתונים של המנהל עם כיסוי, שעות, עומס והתראות"
            caption="נתוני הסידור"
            note="כל תרשים מחושב מאותם שיבוצים ואילוצים שמופיעים בלוח."
            callouts={[{ n: 1, label: "מדדי מפתח", x: "61%", y: "25%" }, { n: 2, label: "עומס וחלוקה", x: "60%", y: "50%" }, { n: 3, label: "אזהרות", x: "62%", y: "82%" }]}
          />
        </TutorialChapter>

        <TutorialChapter number="04" title="לשתף, לייבא ולהוציא קובץ" icon={<FileDown size={19} />}>
          <div className="tutorial-action-list">
            <div><Upload size={18} /><strong>ייבוא</strong><p>העלו Excel או מסמך. פקש מציג תחילה איך הוא קרא אותו; רק ‘אישור הייבוא’ שומר. כללים מוצעים מתחילים לא מסומנים.</p></div>
            <div><FileDown size={18} /><strong>Excel</strong><p>כפתור ‘אקסל’ מוריד את התקופה הנוכחית כקובץ, בלי לשנות את הלוח.</p></div>
            <div><Users size={18} /><strong>קישור לצוות</strong><p>אייקון השיתוף מציג קישור צפייה. החלפת הקישור מבטלת את הקודם.</p></div>
            <div><HelpCircle size={18} /><strong>הגדרות וראיון</strong><p>גלגל השיניים מנהל חיבור מודל וסיסמה; אייקון הנצנוץ פותח מחדש את ראיון ההיכרות.</p></div>
          </div>
        </TutorialChapter>
      </section>

      <section id="team-view" className="tutorial-path tutorial-team" aria-labelledby="team-title">
        <aside className="tutorial-rail" aria-hidden="true"><span>צוות</span></aside>
        <div className="tutorial-section-heading">
          <span>מסלול צפייה</span>
          <h2 id="team-title">הקישור מציג רק מה שפורסם</h2>
          <p>מי שפותח את קישור הצוות רואה את הסידור המלא במצב קריאה בלבד. אין כאן גרירה, מחיקה או אישור.</p>
        </div>
        <Screenshot
          src="/tutorial/team-view.png"
          alt="תצוגת צוות לקריאה בלבד של סידור העבודה"
          caption="תצוגת הצוות"
          note="‘האזור האישי שלי’ מוסיף זהות ושירותים אישיים; הוא אינו משנה את הרשאת הלוח."
          callouts={[{ n: 1, label: "אזור אישי", x: "21%", y: "4%" }, { n: 2, label: "סידור שפורסם", x: "50%", y: "28%" }]}
        />
      </section>

      <section id="employee" className="tutorial-path tutorial-employee" aria-labelledby="employee-title">
        <aside className="tutorial-rail" aria-hidden="true"><span>עובד/ת</span></aside>
        <div className="tutorial-section-heading">
          <span>מסלול עובד/ת</span>
          <h2 id="employee-title">המשמרות, השעות והבקשות — במקום אחד</h2>
          <p>בכניסה הראשונה בוחרים שם ומגדירים קוד אישי. מכאן המערכת מציגה רק את המידע האישי שלכם.</p>
        </div>

        <TutorialChapter number="01" title="לראות מה שובץ ומה השתנה" icon={<UserRound size={19} />}>
          <Screenshot
            src="/tutorial/employee-shifts.png"
            alt="האזור האישי של עובדת עם רשימת המשמרות שלה"
            caption="המשמרות שלי"
            note="אם המנהל הזיז משמרת מאז הביקור האחרון, הודעה תופיע בראש המסך עם הסיבה. ‘ראיתי’ מסמן אותה כנקראה."
            callouts={[{ n: 1, label: "מעבר בין אזורים", x: "46%", y: "10%" }, { n: 2, label: "המשמרות שלכם", x: "46%", y: "28%" }]}
          />
          <FeatureGrid items={[
            ["המשמרות שלי", "תאריך, משמרת והאנשים שעובדים אתכם."],
            ["הנתונים שלי", "שעות, מספר משמרות, כוננויות והוגנות ביחס לצוות."],
            ["הלוח המלא", "אותו סידור שפורסם לצוות, בקריאה בלבד."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="02" title="לשלוח אילוץ או להציע החלפה" icon={<MessageSquareText size={19} />}>
          <Screenshot
            src="/tutorial/employee-requests.png"
            alt="טפסי אילוץ והחלפת משמרות באזור האישי"
            caption="בקשות והחלפות"
            note="בקשה נשארת ‘ממתינה’ עד שהמנהל מחליט. היא אינה משנה את הלוח בעצמה."
            callouts={[{ n: 1, label: "בקשת אילוץ", x: "51%", y: "30%" }, { n: 2, label: "הצעת החלפה", x: "51%", y: "70%" }]}
          />
          <div className="tutorial-checklist">
            <p><Check size={16} /> אילוץ: בחרו תאריך, משמרת, סיבה והאם זו בקשה קשיחה.</p>
            <p><Check size={16} /> אפשר למשוך בקשה כל עוד היא עדיין ממתינה.</p>
            <p><Check size={16} /> החלפה: בחרו משמרת שלכם, עובד אחר והמשמרת שמולכם.</p>
            <p><Check size={16} /> רק אחרי שהעובד השני מסכים והמנהל מאשר, הסידור משתנה.</p>
          </div>
        </TutorialChapter>
      </section>

      <section className="tutorial-finish">
        <span>זה כל המסלול.</span>
        <h2>עכשיו אפשר לפתוח את השבוע ולעבוד.</h2>
        <p>המדריך נשאר זמין מכפתור ‘מדריך’ בתחתית כל מסך.</p>
        <Link href="/">כניסה לפקש <ArrowLeft size={16} /></Link>
      </section>
    </main>
  );
}

function TutorialChapter({ number, title, icon, children }: { number: string; title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <article className="tutorial-chapter">
      <header><span>{number}</span><i>{icon}</i><h3>{title}</h3></header>
      <div className="tutorial-chapter-body">{children}</div>
    </article>
  );
}

function Screenshot({ src, alt, caption, note, callouts }: { src: string; alt: string; caption: string; note: string; callouts: { n: number; label: string; x: string; y: string }[] }) {
  return (
    <figure className="tutorial-screenshot">
      <div className="tutorial-window">
        <div className="tutorial-window-bar"><span /><span /><span /><b>{caption}</b></div>
        <Image src={src} alt={alt} width={1280} height={720} sizes="(max-width: 900px) 100vw, 1100px" />
        {callouts.map((callout) => (
          <span key={callout.n} className="tutorial-callout" style={{ insetInlineStart: callout.x, top: callout.y }}>
            <b>{callout.n}</b><em>{callout.label}</em>
          </span>
        ))}
      </div>
      <figcaption><span>{caption}</span>{note}</figcaption>
    </figure>
  );
}

function FeatureGrid({ items }: { items: string[][] }) {
  return <div className="tutorial-feature-grid">{items.map(([title, copy]) => <div key={title}><strong>{title}</strong><p>{copy}</p></div>)}</div>;
}
