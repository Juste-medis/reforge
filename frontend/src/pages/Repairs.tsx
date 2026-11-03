import { useEffect, useState } from "react";
import { EmptyArt } from "../components/Art";
import { forget, readHistory, type HistoryEntry } from "../lib/history";
import { when } from "../lib/format";
import { href } from "../lib/route";

const STATE_LABEL: Record<string, string> = { running: "In progress", done: "Ready", failed: "Stopped" };

export function Repairs() {
  const [list, setList] = useState<HistoryEntry[]>(() => readHistory());
  useEffect(() => {
    const refresh = () => setList(readHistory());
    window.addEventListener("reforge-history", refresh);
    return () => window.removeEventListener("reforge-history", refresh);
  }, []);
  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">My repairs</p>
        <h1>Pick up where you left off.</h1>
        <p className="lead">Repairs started in this browser. They're remembered on this device only; the server keeps the files.</p>
      </header>
      {list.length === 0 ? (
        <div className="empty">
          <EmptyArt />
          <h2>No repairs yet</h2>
          <p className="muted">Start with a photo of your part, or run one of the examples.</p>
          <div className="actions center">
            <a className="button button-primary" href={href({ name: "new" })}>New repair</a>
            <a className="button button-ghost" href={href({ name: "home", anchor: "examples" })}>See the examples</a>
          </div>
        </div>
      ) : (
        <ul className="repairs">
          {list.map((e) => (
            <li key={e.id} className="repair">
              <a className="repair-link" href={href({ name: "job", id: e.id })}>
                <span className="repair-thumb">
                  {e.state === "done" ? <img src={`/api/jobs/${e.id}/photo.jpg`} alt="" loading="lazy" onError={(ev) => ((ev.target as HTMLImageElement).style.visibility = "hidden")} /> : <EmptyArt />}
                </span>
                <span className="repair-body">
                  <strong>{e.title}</strong>
                  <span className="muted small">{when(e.createdAt)}{e.sample ? " · synthetic example" : ""}</span>
                  <span className="repair-meta">
                    <span className={`state state-${e.state ?? "running"}`}>{STATE_LABEL[e.state ?? "running"]}</span>
                    {e.size && <span>{e.size}</span>}
                    {e.rebuilt && <span className="t-ember">rebuilt</span>}
                  </span>
                </span>
              </a>
              <button type="button" className="icon-button" aria-label={`Remove ${e.title} from this list`} onClick={() => forget(e.id)}>×</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
