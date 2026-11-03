import { useEffect, useState } from "react";
import { getHealth } from "./api";
import { Footer, Header } from "./components/Chrome";
import { useRoute } from "./lib/route";
import { Home } from "./pages/Home";
import { JobPage } from "./pages/JobPage";
import { NewRepair } from "./pages/NewRepair";
import { Repairs } from "./pages/Repairs";
import type { Health } from "./types";

const TITLES: Record<string, string> = {
  home: "Re-Forge: rebuild the part that broke",
  new: "New repair · Re-Forge",
  repairs: "My repairs · Re-Forge",
  job: "Repair · Re-Forge",
};

export default function App() {
  const route = useRoute();
  const [health, setHealth] = useState<Health | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    const check = () => getHealth().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(null));
    check();
    const id = window.setInterval(check, 30_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    document.title = TITLES[route.name];
    if (route.name !== "home") window.scrollTo({ top: 0 });
  }, [route]);

  return (
    <>
      <button type="button" className="skip" onClick={() => document.getElementById("main")?.focus()}>Skip to content</button>
      <Header route={route} health={health} />
      <main id="main" tabIndex={-1}>
        {health === null && (
          <div className="banner" role="alert">The Re-Forge server isn't answering. Start it with <code>uv run reforge-api</code>, then reload.</div>
        )}
        {route.name === "home" && <Home health={health} anchor={route.anchor} />}
        {route.name === "new" && <NewRepair health={health} />}
        {route.name === "repairs" && <Repairs />}
        {route.name === "job" && <JobPage key={route.id} id={route.id} health={health} />}
      </main>
      <Footer />
    </>
  );
}
