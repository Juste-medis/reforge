import { useEffect, useState } from "react";

// Hash routes keep every view linkable and reload-safe without server routing:
//   #/            home            #/new         new repair
//   #/repairs     my repairs      #/job/<id>    a job: progress, then result or error
//   #/studio      flatten tool    #/studio/<id> guide a job: you steer, geometry judges
export type Route =
  | { name: "home"; anchor?: string }
  | { name: "new" }
  | { name: "repairs" }
  | { name: "studio"; id?: string }
  | { name: "job"; id: string };

export function parse(hash: string): Route {
  const path = hash.replace(/^#/, "");
  const job = path.match(/^\/job\/([a-f0-9]{12})$/);
  if (job) return { name: "job", id: job[1] };
  const studio = path.match(/^\/studio(?:\/([a-f0-9]{12}))?$/);
  if (studio) return { name: "studio", id: studio[1] };
  if (path === "/new") return { name: "new" };
  if (path === "/repairs") return { name: "repairs" };
  const anchor = path.match(/^\/#?([a-z-]+)$/)?.[1];
  return { name: "home", anchor };
}

export function href(route: Route): string {
  switch (route.name) {
    case "job":
      return `#/job/${route.id}`;
    case "studio":
      return route.id ? `#/studio/${route.id}` : "#/studio";
    case "new":
      return "#/new";
    case "repairs":
      return "#/repairs";
    default:
      return route.anchor ? `#/${route.anchor}` : "#/";
  }
}

export function go(route: Route): void {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
