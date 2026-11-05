import { useEffect, useState } from "react";
import { readHistory } from "../lib/history";
import { href, type Route } from "../lib/route";
import type { Health } from "../types";
import { Mark } from "./Art";

function useHistoryCount(): number {
  const [count, setCount] = useState(() => readHistory().length);
  useEffect(() => {
    const update = () => setCount(readHistory().length);
    window.addEventListener("reforge-history", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("reforge-history", update);
      window.removeEventListener("storage", update);
    };
  }, []);
  return count;
}

export function HealthPill({ health }: { health: Health | null | undefined }) {
  if (health === undefined) return null;
  if (health === null) {
    return <span className="pill pill-bad" title="The Re-Forge API isn't answering">Server offline</span>;
  }
  if (!health.meta_key_configured) {
    return <span className="pill pill-muted" title="No Meta Model API key on this server: parts are traced without AI">No AI on this server</span>;
  }
  return (
    <span className="pill pill-ok" title={`AI ready: ${health.segmentation_model} finds the part, ${health.reasoning_model} reads the damage`}>
      AI ready
    </span>
  );
}

export function Header({ route, health }: { route: Route; health: Health | null | undefined }) {
  const count = useHistoryCount();
  const at = (name: Route["name"]) => (route.name === name ? "page" : undefined);
  return (
    <header className="header">
      <div className="header-inner">
        <a className="brand" href="#/" aria-label="Re-Forge home">
          <Mark size={28} />
          <span className="wordmark">Re<span className="wordmark-dash">-</span>Forge</span>
        </a>
        <nav className="nav" aria-label="Main">
          <a href={href({ name: "home", anchor: "how" })} className="nav-link hide-sm">How it works</a>
          <a href={href({ name: "home", anchor: "examples" })} className="nav-link hide-sm">Examples</a>
          <a href={href({ name: "studio" })} className="nav-link hide-sm" aria-current={at("studio")}>Studio</a>
          <a href={href({ name: "repairs" })} className="nav-link" aria-current={at("repairs")}>
            My repairs{count > 0 && <span className="count" aria-label={`${count} saved`}>{count}</span>}
          </a>
          <HealthPill health={health} />
          <a href={href({ name: "new" })} className="button button-primary button-sm" aria-current={at("new")}>New repair</a>
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <Mark size={22} />
          <span>Re-Forge</span>
        </div>
        <p>
          Rebuilds broken flat parts from a photo, and says which numbers were measured and which were estimated.
          A reconstruction is not a verified replacement part: check it before you rely on it, and never use it where a failure could hurt someone.
        </p>
        <p className="footer-meta">
          Uses Meta SAM 3.1 and Muse Spark through the Meta Model API · Open source, Apache-2.0
        </p>
      </div>
    </footer>
  );
}
