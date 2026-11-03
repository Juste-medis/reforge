import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

export interface SpecLines {
  points: [number, number][];
  runs: { start: number; end: number; status: string }[];
  holes: { x: number; y: number; d: number; status: string }[];
  thickness: number;
}

const COLOURS: Record<string, number> = { OBSERVED: 0x2563eb, INFERRED: 0xc2410c, UNCERTAIN: 0xb91c1c, MEASURED: 0x0f766e };

function label(text: string): THREE.Sprite {
  const scale = 4;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const font = `600 ${13 * scale}px "Inter Variable", Inter, system-ui, sans-serif`;
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 22 * scale;
  const h = 26 * scale;
  canvas.width = w;
  canvas.height = h;
  ctx.font = font;
  ctx.fillStyle = "rgba(255,255,255,0.96)";
  ctx.beginPath();
  ctx.roundRect(0, 0, w, h, h / 2);
  ctx.fill();
  ctx.fillStyle = "#14161a";
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  ctx.fillText(text, w / 2, h / 2 + scale);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  // Constant size on screen (about 22 px in a 450 px tall view), whatever the part's size or the zoom.
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true,
                                                             sizeAttenuation: false }));
  sprite.userData.aspect = w / h;
  sprite.renderOrder = 10;
  return sprite;
}

function dimension(a: THREE.Vector3, b: THREE.Vector3, offset: THREE.Vector3, text: string): THREE.Group {
  const g = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({ color: 0x5b6270, depthTest: false, transparent: true, opacity: 0.9 });
  const a2 = a.clone().add(offset);
  const b2 = b.clone().add(offset);
  const geo = new THREE.BufferGeometry().setFromPoints([a, a2, a2, b2, b2, b]);
  const lines = new THREE.LineSegments(geo, mat);
  lines.renderOrder = 9;
  g.add(lines);
  const s = label(text);
  const h = 0.03;
  s.scale.set(h * s.userData.aspect, h, 1);
  s.position.copy(a2.clone().add(b2).multiplyScalar(0.5));
  g.add(s);
  return g;
}

export function StlViewer({ url, lines, angleDeg = 0, dims }: {
  url: string;
  lines?: SpecLines | null;
  angleDeg?: number;
  dims?: { length: number; width: number } | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ reset: () => void; top: () => void; setEdges: (v: boolean) => void; setDims: (v: boolean) => void } | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [edges, setEdges] = useState(true);
  const [showDims, setShowDims] = useState(true);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    setStatus("loading");
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setStatus("error");
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.prepend(renderer.domElement);
    renderer.domElement.setAttribute("aria-hidden", "true");
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 20000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.09;
    controls.screenSpacePanning = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0xd9dde4, 2.1));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(-120, -160, 260);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xfff1e6, 0.9);
    rim.position.set(200, 140, 80);
    scene.add(rim);

    const model = new THREE.Group();
    model.rotation.z = (-angleDeg * Math.PI) / 180; // caliper-style: the part's length along x
    scene.add(model);
    const edgeGroup = new THREE.Group();
    const dimGroup = new THREE.Group();
    scene.add(dimGroup);
    model.add(edgeGroup);

    let frame = 0;
    const render = () => {
      frame = 0;
      if (controls.update()) request();
      renderer.render(scene, camera);
    };
    const request = () => {
      if (!frame) frame = requestAnimationFrame(render);
    };
    controls.addEventListener("change", request);

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${h}px`;
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      request();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();

    let home = { pos: new THREE.Vector3(), target: new THREE.Vector3() };
    let topView = { pos: new THREE.Vector3(), target: new THREE.Vector3() };
    let disposed = false;
    new STLLoader().load(
      url,
      (geometry) => {
        if (disposed) return;
        geometry.computeVertexNormals();
        const material = new THREE.MeshStandardMaterial({ color: 0xdfe3e8, metalness: 0.0, roughness: 0.62 });
        const mesh = new THREE.Mesh(geometry, material);
        model.add(mesh);
        model.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 35),
                                         new THREE.LineBasicMaterial({ color: 0x8a909c, transparent: true, opacity: 0.55 })));
        if (lines) {
          const z = lines.thickness + 0.04;
          const closed = [...lines.points, lines.points[0]];
          for (const run of lines.runs) {
            const pts = closed.slice(run.start, run.end + 2).map(([x, y]) => new THREE.Vector3(x, y, z));
            if (pts.length < 2) continue;
            const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
                                        new THREE.LineBasicMaterial({ color: COLOURS[run.status] ?? 0x2563eb, linewidth: 2 }));
            edgeGroup.add(line);
          }
          for (const hole of lines.holes) {
            const curve = new THREE.EllipseCurve(hole.x, hole.y, hole.d / 2, hole.d / 2, 0, Math.PI * 2);
            const pts = curve.getPoints(96).map((p) => new THREE.Vector3(p.x, p.y, z));
            edgeGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
                                         new THREE.LineBasicMaterial({ color: COLOURS[hole.status] ?? 0x2563eb })));
          }
        }
        model.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(mesh);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const span = Math.max(size.x, size.y, 10);
        const grid = new THREE.GridHelper(Math.ceil((span * 2.2) / 10) * 10, Math.ceil((span * 2.2) / 10), 0xc9ced6, 0xe4e7ec);
        grid.rotation.x = Math.PI / 2;
        grid.position.set(center.x, center.y, -0.01);
        scene.add(grid);
        if (dims) {
          const o = span * 0.12;
          dimGroup.add(dimension(new THREE.Vector3(box.min.x, box.min.y, 0), new THREE.Vector3(box.max.x, box.min.y, 0),
                                 new THREE.Vector3(0, -o, 0), `${dims.length.toFixed(2)} mm`));
          dimGroup.add(dimension(new THREE.Vector3(box.max.x, box.min.y, 0), new THREE.Vector3(box.max.x, box.max.y, 0),
                                 new THREE.Vector3(o, 0, 0), `${dims.width.toFixed(2)} mm`));
        }
        const r = Math.max(size.length() / 2, 5) * (dims ? 1.25 : 1); // room for the dimension labels
        home = { pos: new THREE.Vector3(center.x - r * 1.25, center.y - r * 2.1, center.z + r * 1.55), target: center.clone() };
        topView = { pos: new THREE.Vector3(center.x, center.y - 0.001, center.z + r * 3.1), target: center.clone() };
        camera.position.copy(home.pos);
        controls.target.copy(home.target);
        controls.minDistance = r * 0.6;
        controls.maxDistance = r * 12;
        controls.update();
        setStatus("ready");
        request();
      },
      undefined,
      () => !disposed && setStatus("error"),
    );

    api.current = {
      reset: () => {
        camera.position.copy(home.pos);
        controls.target.copy(home.target);
        request();
      },
      top: () => {
        camera.position.copy(topView.pos);
        controls.target.copy(topView.target);
        request();
      },
      setEdges: (v) => {
        edgeGroup.visible = v;
        request();
      },
      setDims: (v) => {
        dimGroup.visible = v;
        request();
      },
    };

    return () => {
      disposed = true;
      api.current = null;
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((obj) => {
        const o = obj as THREE.Mesh;
        if (o.geometry) o.geometry.dispose();
        const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
        if (m) (Array.isArray(m) ? m : [m]).forEach((mm) => {
          (mm as THREE.SpriteMaterial).map?.dispose();
          mm.dispose();
        });
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [url, lines, angleDeg, dims]);

  useEffect(() => api.current?.setEdges(edges), [edges, status]);
  useEffect(() => api.current?.setDims(showDims), [showDims, status]);

  return (
    <div className="viewer" ref={host}>
      {status !== "ready" && (
        <div className="viewer-status" role="status">
          {status === "loading" ? "Loading the 3D model…" : "The 3D preview isn't available in this browser. The download below still works."}
        </div>
      )}
      <div className="viewer-tools" role="toolbar" aria-label="3D view">
        <button type="button" onClick={() => api.current?.reset()}>Reset</button>
        <button type="button" onClick={() => api.current?.top()}>Top view</button>
        {lines && (
          <button type="button" aria-pressed={edges} onClick={() => setEdges((v) => !v)} title="Edges coloured by where they came from">Evidence</button>
        )}
        {dims && (
          <button type="button" aria-pressed={showDims} onClick={() => setShowDims((v) => !v)}>Sizes</button>
        )}
      </div>
      <p className="viewer-hint">Drag to rotate · scroll or pinch to zoom · right-drag or two fingers to pan</p>
    </div>
  );
}

export default StlViewer;
