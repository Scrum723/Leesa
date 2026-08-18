import styles from "./page.module.css";

const RAILWAY = "https://social-media-liaison-production.up.railway.app";

const links = [
  { href: `${RAILWAY}/`, label: "Open LEESA Dashboard", desc: "Accounts, queue, analytics, library" },
  { href: `${RAILWAY}/legal`, label: "Legal Center", desc: "All policies in one place" },
  { href: `${RAILWAY}/legal/terms`, label: "Terms of Service", desc: "Rules for using LEESA" },
  { href: `${RAILWAY}/legal/privacy`, label: "Privacy Policy", desc: "How we handle your data" },
  { href: `${RAILWAY}/legal/data-collection`, label: "Data Collection", desc: "What we collect and why" },
  { href: `${RAILWAY}/legal/violations`, label: "Violations & Acceptable Use", desc: "Prohibited conduct" },
  { href: "https://linktr.ee/URP", label: "linktr.ee/URP", desc: "Doc Weather links hub" },
  { href: "https://github.com/Scrum723/Leesa", label: "GitHub Repository", desc: "Source code & Actions" },
  {
    href: "./tiktokIcaeOgyGv3nJ5KFUdhGxO6SiUVLmaTy8-2.txt",
    label: "TikTok site verification file",
    desc: "Must return plain text for Developer Portal verify",
  },
];

export default function Home() {
  return (
    <main className={styles.main}>
      <header className={styles.hero}>
        <p className={styles.kicker}>Doc Weather · Charles Clottin</p>
        <h1>LEESA</h1>
        <p className={styles.subtitle}>
          Social Media Liaison — post videos &amp; writing to X, Instagram, TikTok, and YouTube
          with AI captions, engagement, analytics, and a Mac + Railway control room.
        </p>
      </header>

      <section className={styles.grid}>
        {links.map((l) => (
          <a key={l.href} className={styles.card} href={l.href} target="_blank" rel="noreferrer">
            <strong>{l.label}</strong>
            <span>{l.desc}</span>
          </a>
        ))}
      </section>

      <footer className={styles.footer}>
        <p>Stay accurate. Stay informed.</p>
        <p className={styles.muted}>Public site · Dashboard hosted on Railway</p>
      </footer>
    </main>
  );
}
