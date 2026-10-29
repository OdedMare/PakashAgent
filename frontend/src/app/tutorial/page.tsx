import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { Guard } from "@/components/Crew/Guard";
import type { Who } from "@/components/Crew/Guard";
import {
  ArrowLeft,
  ArrowLeftRight,
  BarChart3,
  Bot,
  CalendarCheck,
  Check,
  FileDown,
  HelpCircle,
  Inbox,
  MessageSquareText,
  MousePointer2,
  Repeat2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  Users,
} from "lucide-react";

export const metadata: Metadata = {
  title: "מדריך משמרות זהב — כל המערכת, צעד אחר צעד",
  description: "מדריך מצולם למנהלים ולעובדים במערכת משמרות זהב",
};

export default function TutorialPage() {
  return (
    <main id="main-content" className="tutorial-page">
      <header className="tutorial-topbar">
        <Link href="/" className="tutorial-brand" aria-label="חזרה למשמרות זהב">
          <span className="tutorial-brand-mark"><CalendarCheck size={17} /></span>
          <span><strong>משמרות זהב</strong><small>מדריך שימוש</small></span>
        </Link>
        <Link href="/" className="tutorial-back">למערכת <ArrowLeft size={15} /></Link>
      </header>

      <section className="tutorial-hero" aria-labelledby="tutorial-title">
        <div className="tutorial-hero-copy">
          <div className="tutorial-crew">
            <span className="guide-crew-pair" aria-hidden="true"><Guard who="him" /><Guard who="her" /></span>
            <p>היי, אנחנו נלווה אתכם במדריך. בחרו מסלול ונראה לכם בדיוק איפה כל דבר נמצא.</p>
          </div>
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
          <div className="route-stop is-active"><b>כניסה והגדרה</b><small>הצוות, הזהות ושיטת השיבוץ</small></div>
          <span className="route-time">15:00</span>
          <div className="route-stop"><b>בנייה ובדיקה</b><small>בנייה, שיחה עם הסוכן ואזהרות</small></div>
          <span className="route-time">23:00</span>
          <div className="route-stop"><b>פרסום וטיפול</b><small>הצוות רואה ומגיש בקשות</small></div>
        </div>
      </section>

      <section className="tutorial-orientation" aria-labelledby="start-title">
        <div className="tutorial-section-heading">
          <span>נקודת פתיחה</span>
          <h2 id="start-title">נכנסים למרחב הנכון</h2>
          <p>בוחרים צוות, ואז דלת: מנהל עם סיסמת הצוות, או עובד/ת עם שם וקוד אישי. לצוות יש גם קישור צפייה בלי סיסמה.</p>
        </div>
        <Screenshot
          src="/tutorial/login.png"
          alt="מסך הכניסה למשמרות זהב, עם בחירת צוות, בחירה בין מנהל לעובד/ת ושדה סיסמה"
          caption="מסך הכניסה"
          note="צוות חדש לא נפתח כאן: צוות משמרות זהב פותח אותו ומוסר למנהל שם וסיסמה."
          callouts={[{ n: 1, label: "בוחרים צוות", x: "39%", y: "67%" }, { n: 2, label: "מנהל או עובד/ת", x: "39%", y: "78%" }, { n: 3, label: "סיסמה או קוד אישי", x: "39%", y: "90%" }]}
        />
        <div className="tutorial-first-steps">
          <article><span>1</span><h3>מקבלים צוות</h3><p>צוות משמרות זהב פותח את הצוות ומוסר שם וסיסמה. שום לוח, כלל או שיחה לא עוברים בין צוותים.</p></article>
          <article><span>2</span><h3>מגדירים את היחידה</h3><p>טופס אחד מרכז כוח אדם, סוגי משמרות ותקינה, סבבים ותלתונים, גבולות עומס וכללים — ללא שימוש במודל.</p></article>
          <article><span>3</span><h3>בוחרים איך להתחיל</h3><p>בונים סידור לטווח שבוחרים, או פותחים שבוע ריק ומשבצים ידנית.</p></article>
        </div>
        <Screenshot
          src="/tutorial/manager-setup.png"
          alt="טופס הגדרת היחידה עם פרטי היחידה, ימי פעילות וסבבים ותלתונים"
          caption="הגדרת היחידה"
          note="בסבב מגדירים רק את קבוצה א׳ — הסופ״ש שבו היא סוגרת ושעות הסגירה. שאר הקבוצות נגזרות ממנה, והתאריכים שליד העוגן הם תצוגה מקדימה."
          callouts={[{ n: 1, label: "היחידה והיציאות", x: "17%", y: "22%" }, { n: 2, label: "סבבים ותלתונים", x: "17%", y: "58%" }, { n: 3, label: "שמירה", x: "78%", y: "93%" }]}
        />
        <FeatureGrid items={[
          ["כוח אדם", "שם, תפקיד, סבב וקבוצה, מעמד (תקן, חפיפה, נחפף/ת) והסמכה למפקד/ת משמרת."],
          ["סוגי משמרות ותקינה", "שעות, ימים, כמה אנשים בכל משמרת ואילו תפקידים מוסמכים לעמוד בה."],
          ["גבולות וכללים", "עומס, מנוחה וכללים קבועים במילים שלכם. ‘מה הקוד הבין’ מראה איך כל משפט תורגם."],
        ]} />
        <div className="tutorial-note"><HelpCircle size={16} /> במסך ההגדרה עצמו לחצו על ‘עזרה’ כדי לפתוח סיור שמצביע על כל חלק בטופס. מחזור ימים כמו 11/3, 12/2 או שבוע־שבוע מוגדר שם באותו אופן: ימים בבסיס ובבית, עוגן לקבוצה א׳ ושעות.</div>
        <p className="tutorial-note">שמירה שמוסיפה חייל או משמרת משלבת אותם בכל טיוטה מהיום והלאה, בלי לערבב את מה שכבר שובץ. כל שינוי אחר חל על הבנייה הבאה. אפשר לחזור לטופס בכל עת מאייקון המחוונים בסרגל העליון.</p>
      </section>

      <section id="manager" className="tutorial-path tutorial-manager" aria-labelledby="manager-title">
        <aside className="tutorial-rail" aria-hidden="true"><span>מנהל/ת</span></aside>
        <div className="tutorial-section-heading">
          <span>מסלול מנהל/ת</span>
          <h2 id="manager-title">מכינים שבוע, בודקים, ורק אז מפרסמים</h2>
          <p>בסרגל הצד ארבעה מסכים: סוכן הסידור, לוח המשמרות, כוח אדם וסקירה. הסוכן נפתח לצד הלוח, כדי שלא תאבדו את ההקשר.</p>
        </div>
        <Narrator who="him">
          אני אסביר את צד המנהל: בונים שבוע עם הסוכן או ידנית, בודקים את האזהרות, ורק אז מפרסמים לצוות.
        </Narrator>

        <TutorialChapter number="01" title="להגדיר סבבים ותלתונים" icon={<Repeat2 size={19} />}>
          <p>בכרטיס של כל סבב (שבת אחת משתיים), תלתון (אחת משלוש) ורבעון (אחת מארבע — מפעילים אותו ב״מבני יציאה אופציונליים״) עונים על שלוש שאלות, רק עבור קבוצה א׳. המערכת מחשבת מהן את התור של כל קבוצה אחרת, ומתחת לשאלות מראה את שמונת הסופ״שים הקרובים — עוד לפני השמירה.</p>
          <Screenshot
            src="/tutorial/rotation-setup.png"
            alt="כרטיס הסבב במסך הגדרת היחידה: תאריך העוגן, בחירת סוג הסבב ושעות הכניסה והיציאה"
            caption="הגדרת סבב — שלבים 1 ו־2"
            note="בוחרים את סוג הסבב בלחיצה. השעות שמתחת מתמלאות לבד — החילוף בסוף המשמרת הראשונה של יום ראשון — ואפשר לשנות אותן."
            callouts={[{ n: 1, label: "תאריך מסופ״ש של א׳", x: "29%", y: "32%" }, { n: 2, label: "סוג הסבב", x: "29%", y: "49%" }, { n: 3, label: "שעות כניסה ויציאה", x: "29%", y: "66%" }]}
          />
          <div className="tutorial-two-column">
            <div><CalendarCheck size={18} /><h3>1. מתי קבוצה א׳ סוגרת?</h3><p>בוחרים תאריך כלשהו מסופ״ש אחד שבו א׳ בבסיס — השבת, החמישי או השישי של אותו סופ״ש. לא צריך תאריך לכל קבוצה: ב׳ (ובתלתון גם ג׳) מקבלות את התור שלהן מכאן.</p></div>
            <div><Repeat2 size={18} /><h3>2. איזה סוג סבב?</h3><p>ימים בבסיס / ימים בבית, בשבועיים של הסבב: <b>11/3</b> (ברירת המחדל — הבית מחמישי), <b>12/2</b> (מחמישי עבודה רגילה, הבית משישי), <b>10/4</b> (הבית מרביעי), <b>שבוע־שבוע</b> — או ״ימים ושעות אחרים״. הבחירה חלה על כל הקבוצות, כל אחת בתורה.</p></div>
          </div>
          <Screenshot
            src="/tutorial/rotation-exceptions.png"
            alt="סופ״ש חריג בשם חג עם תאריך וסוג משלו, ומתחתיו רצועת הסופ״שים הקרובים"
            caption="סופ״שים חריגים ותצוגה מקדימה"
            note="סופ״ש חריג משנה רק את אותו סופ״ש. הסבב עצמו לא זז — ברצועה הסופ״ש החריג מסומן בצבע ובשם שנתתם לו."
            callouts={[{ n: 1, label: "תאריך הסופ״ש", x: "30%", y: "22%" }, { n: 2, label: "הסוג בסופ״ש הזה", x: "30%", y: "41%" }, { n: 3, label: "בדיקה לפני שמירה", x: "29%", y: "83%" }]}
          />
          <p>3. <strong>סופ״שים חריגים.</strong> לחג או לאירוע: לוחצים ״הוספת סופ״ש חריג״, בוחרים תאריך כלשהו באותו סופ״ש, נותנים שם (רשות) ובוחרים לו סוג משלו. ״להחיל על כמה סופ״שים ברצף״ הופך אותו לטווח — למשל לכל תקופת החגים.</p>
          <FeatureGrid items={[
            ["סבב 11/3", "שלב 2: משאירים ״11/3״. אין צורך להזין שעות."],
            ["סבב 12/2", "שלב 2: ״12/2״. הסגירה מתחילה בשישי, וחמישי הוא יום עבודה רגיל לכולם."],
            ["סבב 10/4", "שלב 2: ״10/4״. הקבוצה שלא סוגרת יוצאת כבר ברביעי."],
            ["שבוע בבסיס, שבוע בבית", "שלב 2: ״שבוע־שבוע״. החילוף ביום ראשון, בשעה שמתחת."],
            ["חג שמאריך את היציאה", "שלב 3: סופ״ש חריג בשם החג, תאריך מתוך אותו סופ״ש, וסוג אחר — למשל ״10/4״ או ״ימים ושעות אחרים״."],
            ["לפני ששומרים", "בודקים ברצועה ״כך ייראו הסופ״שים הקרובים״ שהקבוצה והשעות נכונות בכל סופ״ש."],
          ]} />
          <p>קבוצה שלא נמצאת ביום קבוע (למשל ״סבב ב׳ לא נמצאת בשלישי״) מוגדרת בתחתית הכרטיס, תחת ״מתקדם״. מחזור שלא בנוי על סופ״שים — ימים בבסיס וימים בבית לפי לוח משלו — מוגדר מתחת לכרטיסים, ב״מחזורי ימים״.</p>
        </TutorialChapter>

        <TutorialChapter number="02" title="לקרוא את הלוח" icon={<CalendarCheck size={19} />}>
          <p>בוחרים כמה רואים: יום, שבוע, שבועיים או חודש. ביום ובשבוע משבצים ועורכים; שבועיים וחודש הם מבט־על לקריאה — לחיצה על יום או שבוע פותחת אותו. מסילת השבוע והאריחים מסכמים איוש, משמרות פתוחות, התנגשויות ושעות, ולחיצה על אריח מסננת את הלוח.</p>
          <Screenshot
            src="/tutorial/manager-board.png"
            alt="לוח המשמרות של המנהל עם בורר תצוגה, פעולות שבוע, מסילת שבוע, מדדי איוש ורשת משמרות"
            caption="לוח המשמרות"
            note="ראש כל עמודה מציין של איזו קבוצה הסגירה, ויום חילוף מסומן. אזהרה מיידעת ואינה חוסמת פרסום."
            callouts={[{ n: 1, label: "תצוגה וניווט", x: "45%", y: "11%" }, { n: 2, label: "פעולות השבוע", x: "62%", y: "11%" }, { n: 3, label: "מצב השבוע", x: "28%", y: "33%" }, { n: 4, label: "פעולות ליום", x: "33%", y: "58%" }, { n: 5, label: "מפקד/ת ונחפף/ת", x: "26%", y: "86%" }]}
          />
          <FeatureGrid items={[
            ["שיבוץ ידני", "לחצו על + בתא ריק ובחרו עובד — נשמר מיד. הסרה נעשית מכרטיס השיבוץ."],
            ["העברה", "גררו שיבוץ קיים. המערכת מציגה את ההשפעה ומבקשת סיבה לפני שהשינוי נשמר."],
            ["פעולות ליום", "‘סוכן ליום’ פותח את הסוכן על אותו יום, ‘בנייה מכאן’ בונה מהיום הזה, ‘נקה יום’ מרוקן אותו."],
            ["ניקוי ומחיקה", "‘ניקוי השבוע’ מרוקן שיבוצים ומשאיר את השורות; ‘מחיקת הסידור’ מחזירה את השבוע למצב שלפני בנייה."],
            ["סדר השורות", "השורות מסודרות לפי שעת ההתחלה. אפשר לגרור לסדר אחר — זה נשמר בדפדפן ולא משנה את הסידור."],
            ["פרסום", "‘פרסום לצוות’ הוא הרגע שבו העובדים רואים את הגרסה. שבוע מפורסם נעול לעריכה עד שמחזירים אותו לטיוטה."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="03" title="לבנות סידור — כולו או רק חלק" icon={<Sparkles size={19} />}>
          <p>‘בניית הסידור לשבוע’ בשבוע ריק, או ‘בנייה מכאן’ בראש עמודה, פותחים את חלון הבנייה. בוחרים מתאריך ועד תאריך, אילו סוגי משמרות לשבץ, ומוסיפים הנחיות לתקופה אם צריך.</p>
          <Screenshot
            src="/tutorial/manager-generate.png"
            alt="חלון בניית ימים בסידור הקיים, עם טווח תאריכים, בחירת סוגי משמרות והנחיות"
            caption="בניית הסידור"
            note="מה ששובץ ידנית נשאר במקומו, והבנייה ממלאת סביבו. רק הימים והמשמרות שבחרתם נבנים מחדש."
            callouts={[{ n: 1, label: "טווח התאריכים", x: "36%", y: "36%" }, { n: 2, label: "סוגי משמרות", x: "36%", y: "63%" }, { n: 3, label: "שמירה על הקיים", x: "36%", y: "88%" }]}
          />
          <div className="tutorial-checklist">
            <p><Check size={16} /> הבנייה רצה ברקע: הלוח נשאר פתוח, ואפשר להמשיך לשבץ ידנית בזמן שהיא עובדת.</p>
            <p><Check size={16} /> הפס בראש המסך סופר ימים ומראה מה נעשה עכשיו. ‘עצירת היצירה’ שומרת כל יום שכבר נבנה.</p>
            <p><Check size={16} /> בנייה שנעצרה או נכשלה ממשיכה מהיום הבא בלחיצה, וכשל מגיע עם הסיבה.</p>
            <p><Check size={16} /> ‘שמירה על השיבוץ הקיים’ מזיזה רק את מה שצריך כדי לשלב חייל או משמרת חדשים.</p>
          </div>
        </TutorialChapter>

        <TutorialChapter number="04" title="לדבר עם הסוכן — בלי לתת לו לכתוב לבד" icon={<Bot size={19} />}>
          <p>‘סוכן הסידור’ פותח שיחה לצד הלוח. כותבים שאלה או בקשה במילים שלכם, באותה תיבה. שאלה מקבלת תשובה ולא משנה דבר; בקשה לשינוי חוזרת כתוכנית, ושום דבר לא נשמר עד ‘החלת התוכנית’.</p>
          <Screenshot
            src="/tutorial/manager-agent.png"
            alt="לוח המנהל לצד שיחה עם סוכן הסידור, עם הצעות פתיחה ותיבת כתיבה"
            caption="סוכן הסידור"
            note="הסוכן עובד על השבוע שמוצג בלוח. ההצעות בפתיחה נגזרות מהאזהרות והבקשות הפתוחות."
            callouts={[{ n: 1, label: "כלי ניהול", x: "20%", y: "11%" }, { n: 2, label: "הצעות פתיחה", x: "20%", y: "60%" }, { n: 3, label: "שאלה או בקשה", x: "22%", y: "87%" }, { n: 4, label: "השיחות שלך", x: "2%", y: "36%" }]}
          />
          <div className="tutorial-two-column">
            <div><MessageSquareText size={18} /><h3>כשאתם שואלים</h3><p>תקבלו תשובה מתוך הנתונים — למשל ‘מי יכול להחליף ברביעי?’ או ‘מה חסר לך כדי לבנות?’. אין כפתור אישור, כי דבר לא השתנה.</p></div>
            <div><MousePointer2 size={18} /><h3>כשאתם מבקשים שינוי</h3><p>תראו את השינויים, את הנימוק ואת האזהרות הצפויות. חריגה מוצגת דורשת סימון מפורש לפני ‘החלת התוכנית’.</p></div>
          </div>
          <FeatureGrid items={[
            ["שיחות", "‘שיחה חדשה’, חיפוש והיסטוריה בסרגל הצד. השיחות שמורות ופרטיות לדפדפן שבו נכנסתם."],
            ["יום אחד", "‘סוכן ליום’ ממקד את השיחה בתאריך אחד; תוכנית לאותו יום בונה רק אותו."],
            ["גודל ומקום", "גוררים את המפריד בין השיחה ללוח; לחיצה כפולה מאפסת. ה־X סוגר את הסוכן והלוח מתרחב."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="05" title="שינויים: החלפה, חייל חדש, משמרת חדשה" icon={<ArrowLeftRight size={19} />}>
          <p>לשונית ‘שינויים’ במגירה מרכזת את שלושת השינויים השכיחים, ושומרת על הסידור הקיים ככל האפשר.</p>
          <Screenshot
            src="/tutorial/manager-changes.png"
            alt="לשונית השינויים עם החלפת משמרת, הוספת חייל והוספת משמרת"
            caption="שינויים"
            note="ההחלפה לא נשמרת מכאן: הבחירה עוברת לשיחה כתוכנית, ושם מאשרים אותה."
            callouts={[{ n: 1, label: "שלוש פעולות", x: "20%", y: "28%" }, { n: 2, label: "מי, למה ומתי", x: "20%", y: "47%" }]}
          />
          <FeatureGrid items={[
            ["החלפת משמרת", "בוחרים מי לא זמין/ה, סיבה וטווח תאריכים. המחליפים מסודרים כך שהעומס יתחלק הכי שווה."],
            ["הוספת חייל", "אותו טופס כמו בהגדרת היחידה. אחרי השמירה החייל משתלב בכל טיוטה מהיום והלאה."],
            ["הוספת משמרת", "סוג משמרת חדש מתווסף ומאויש סביב השיבוצים שכבר קיימים. שבוע מפורסם לא נוגעים בו."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="06" title="בקשות, החלפות והעדפות" icon={<Inbox size={19} />}>
          <p>לשונית ‘בקשות’ מציגה אילוצים שעובדים שלחו והחלפות ששני העובדים כבר הסכימו עליהן. בקשה חדשה קופצת גם כהודעה בזמן אמת.</p>
          <Screenshot
            src="/tutorial/manager-requests.png"
            alt="לשונית הבקשות עם בקשת אילוץ של עובדת, שדה סיבה וכפתורי אישור ודחייה"
            caption="בקשות"
            note="אישור הוא לחיצה אחת; דחייה דורשת סיבה, והעובד/ת רואה אותה."
            callouts={[{ n: 1, label: "אישור או דחייה", x: "20%", y: "33%" }]}
          />
          <FeatureGrid items={[
            ["אילוצים", "בקשה מאושרת נשמרת כ‘העובד מסר’ — נפרד ממה שהמנהל קבע."],
            ["החלפות", "מגיעות להכרעה רק אחרי שהעמית הסכים. בשבוע מפורסם צריך קודם להחזיר לטיוטה."],
            ["העדפות", "בלשונית ‘צוות’: מה שהסוכן זוכר. הצעה שלו אינה פעילה עד שתאשרו, וכל העדפה ניתנת לעריכה, השבתה ומחיקה."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="07" title="כוח אדם" icon={<Users size={19} />}>
          <p>מסך ‘כוח אדם’ מרכז את אנשי הצוות, סוגי המשמרות והאילוצים, עם מספר המשמרות והשעות של כל אחד.</p>
          <Screenshot
            src="/tutorial/manager-team.png"
            alt="מסך כוח אדם ותקינה עם רשימת אנשי הצוות, הסבב, התגים והעומס של כל אחד"
            caption="כוח אדם ותקינה"
            note="כל אילוץ מסומן במקור שלו: המנהל קבע, הסוכן רשם או העובד מסר."
            callouts={[{ n: 1, label: "סבב, מעמד ותגים", x: "22%", y: "35%" }, { n: 2, label: "עריכה והוצאה", x: "84%", y: "35%" }]}
          />
          <FeatureGrid items={[
            ["עריכה", "העיפרון פותח את פרטי האדם; ‘הוספת עובד/ת’ בתחתית הרשימה."],
            ["הוצאה מהסגל", "בוחרים מאיזה תאריך. המערכת סופרת קודם כמה משמרות יתפנו ואילו שבועות מפורסמים יחזרו לטיוטה."],
            ["החזרה לסגל", "מי שסיים עובר ל‘עובדים שסיימו’; ההיסטוריה שלו נשמרת ואפשר להחזיר אותו."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="08" title="לבדוק את התמונה הרחבה" icon={<BarChart3 size={19} />}>
          <p>מסך ‘סקירה’ מתרגם את הלוח למספרים: איוש, משמרות, לילות לכל חייל/ת, התנגשויות ואילוצים. המספרים מסבירים את הלוח — הם לא נותנים לו ציון.</p>
          <Screenshot
            src="/tutorial/manager-analytics.png"
            alt="מסך הסקירה עם בורר טווח, מדדי מפתח, משמרות לפי חייל ושיבוצים לפי יום"
            caption="סקירה"
            note="כל מספר מחושב בשרת מאותם שיבוצים ואזהרות שמופיעים בלוח."
            callouts={[{ n: 1, label: "טווח וחייל/ת", x: "40%", y: "44%" }, { n: 2, label: "מדדי מפתח", x: "30%", y: "56%" }, { n: 3, label: "עומס לכל אחד", x: "62%", y: "76%" }]}
          />
          <FeatureGrid items={[
            ["טווח", "התקופה, יום, שבוע, חודש או טווח חופשי — וגם חייל/ת אחד/ת."],
            ["עומס", "משמרות ולילות לכל אחד, לפי הסבב שלו. השעות מופיעות בריחוף."],
            ["מה שחוזר על עצמו", "הצעות לכללים לפי התיקונים שעשיתם בסידור. הצעות בלבד — שום דבר לא הופך לכלל לבד."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="09" title="לשתף, להוציא קובץ ולקבל עזרה" icon={<FileDown size={19} />}>
          <div className="tutorial-action-list">
            <div><FileDown size={18} /><strong>Excel</strong><p>כפתור ‘אקסל’ מוריד את השבוע כקובץ, בלי לשנות את הלוח.</p></div>
            <div><Users size={18} /><strong>קישור לצוות</strong><p>אייקון השיתוף מציג קישור צפייה. החלפת הקישור מבטלת את הקודם לכולם.</p></div>
            <div><SlidersHorizontal size={18} /><strong>הגדרת יחידה</strong><p>אייקון המחוונים פותח את הגדרת היחידה, הסבבים והתלתונים. ליד נמצאים מצב כהה ותפריט החשבון ליציאה.</p></div>
            <div><HelpCircle size={18} /><strong>עזרה</strong><p>‘עזרה’ (או המקש ?) פותח סיור מודרך במסך, צעדים ראשונים, קיצורי מקלדת ומילון מונחים.</p></div>
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
        <Narrator who="her">
          כאן רק מסתכלים: הקישור מראה את הסידור שפורסם, ואי אפשר לשנות בו כלום.
        </Narrator>
        <Screenshot
          src="/tutorial/team-view.png"
          alt="תצוגת צוות לקריאה בלבד של סידור העבודה"
          caption="תצוגת הצוות"
          note="אייקון האזור האישי מאפשר לבחור שם ולהגדיר קוד אישי. אחר כך נכנסים ישירות מ‘עובד/ת’ במסך הכניסה."
          callouts={[{ n: 1, label: "אזור אישי", x: "85%", y: "7%" }, { n: 2, label: "סידור שפורסם", x: "45%", y: "30%" }]}
        />
      </section>

      <section id="employee" className="tutorial-path tutorial-employee" aria-labelledby="employee-title">
        <aside className="tutorial-rail" aria-hidden="true"><span>עובד/ת</span></aside>
        <div className="tutorial-section-heading">
          <span>מסלול עובד/ת</span>
          <h2 id="employee-title">המשמרות, השינויים והבקשות — במקום אחד</h2>
          <p>בפעם הראשונה נכנסים מקישור הצוות, בוחרים שם ומגדירים קוד אישי. מאז נכנסים מ‘עובד/ת’ במסך הכניסה, עם השם והקוד.</p>
        </div>
        <Narrator who="her">
          ואני אסביר את צד העובד: רואים את המשמרות שלכם, מה השתנה, ושולחים בקשות ואילוצים למנהל.
        </Narrator>

        <TutorialChapter number="01" title="לראות מה שובץ ומה השתנה" icon={<UserRound size={19} />}>
          <Screenshot
            src="/tutorial/employee-shifts.png"
            alt="האזור האישי של עובדת עם הודעה על שינוי, רשימת המשמרות שלה ושינויים שנגעו לה"
            caption="המשמרות שלי"
            note="אם משמרת שלכם זזה מאז הביקור האחרון, הודעה מופיעה בראש המסך עם הסיבה. ‘ראיתי’ מסמן שקראתם — זה לא אישור ולא הסכמה."
            callouts={[{ n: 1, label: "מה השתנה", x: "26%", y: "13%" }, { n: 2, label: "שלוש לשוניות", x: "30%", y: "24%" }, { n: 3, label: "שינויים שנגעו לי", x: "24%", y: "84%" }]}
          />
          <FeatureGrid items={[
            ["המשמרות שלי", "תאריך, משמרת והאנשים שעובדים אתכם, ומתחת — השינויים שנגעו לכם."],
            ["בקשות והחלפות", "אילוצים שהגשתם והחלפות מול עמיתים, עם המצב של כל אחד."],
            ["הלוח המלא", "אותו סידור שפורסם לצוות, בקריאה בלבד."],
          ]} />
        </TutorialChapter>

        <TutorialChapter number="02" title="לשלוח אילוץ או להציע החלפה" icon={<MessageSquareText size={19} />}>
          <Screenshot
            src="/tutorial/employee-requests.png"
            alt="טופס בקשת אילוץ ורשימת הבקשות שלי באזור האישי"
            caption="בקשות והחלפות"
            note="בקשה נשארת ‘ממתינה לאישור’ עד שהמנהל מחליט. היא אינה משנה את הלוח בעצמה."
            callouts={[{ n: 1, label: "בקשת אילוץ", x: "26%", y: "34%" }, { n: 2, label: "הבקשות שלי", x: "26%", y: "80%" }]}
          />
          <div className="tutorial-checklist">
            <p><Check size={16} /> אילוץ: בחרו תאריך, משמרת (או כל היום) וסיבה. ‘אני דווקא כן יכול/ה לעבוד אז’ מסמן זמינות במקום חסימה.</p>
            <p><Check size={16} /> אפשר לבטל בקשה כל עוד היא ממתינה. דחייה מגיעה עם הסיבה של המנהל.</p>
            <p><Check size={16} /> החלפה: בחרו משמרת שלכם ומשמרת של עובד אחר. העמית מקבל התראה ועונה מהאזור האישי שלו.</p>
            <p><Check size={16} /> רק אחרי שהעמית מסכים והמנהל מאשר, הסידור משתנה.</p>
          </div>
        </TutorialChapter>
      </section>

      <section className="tutorial-finish">
        <span>זה כל המסלול.</span>
        <h2>עכשיו אפשר לפתוח את השבוע ולעבוד.</h2>
        <p>המדריך נשאר זמין מכפתור ‘עזרה’ בכל מסך, תחת ‘המדריך המלא’.</p>
        <Link href="/">כניסה למשמרות זהב <ArrowLeft size={16} /></Link>
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
        <Image src={src} alt={alt} width={1280} height={720} sizes="(max-width: 900px) 100vw, 1100px" unoptimized />
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

/** One of the two guards introducing a path, in a speech bubble. */
function Narrator({ who, children }: { who: Who; children: React.ReactNode }) {
  return (
    <div className="tutorial-crew">
      <span className="guide-guard" aria-hidden="true"><Guard who={who} /></span>
      <p>{children}</p>
    </div>
  );
}
