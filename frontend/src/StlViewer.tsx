import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

/** Renders the validated STL exactly as downloaded: z up, 10 mm grid on the print bed. */
export function StlViewer({ url }: { url: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    setStatus("loading");
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xdfe7ff, 0x2a2f38, 1.7));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.8);
    keyLight.position.set(80, -140, 180);
    scene.add(keyLight);

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();

    let disposed = false;
    new STLLoader().load(
      url,
      (geometry) => {
        if (disposed) return;
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
        const sphere = geometry.boundingSphere ?? new THREE.Sphere(new THREE.Vector3(), 50);
        const material = new THREE.MeshStandardMaterial({ color: 0x3f7fdc, metalness: 0.05, roughness: 0.55 });
        scene.add(new THREE.Mesh(geometry, material));
        scene.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), new THREE.LineBasicMaterial({ color: 0x0a1a33 })));
        const cells = Math.max(2, Math.ceil((sphere.radius * 2.6) / 10));
        const grid = new THREE.GridHelper(cells * 10, cells, 0x56627a, 0x2b3240);
        grid.rotation.x = Math.PI / 2;
        grid.position.set(sphere.center.x, sphere.center.y, 0);
        scene.add(grid);
        const r = sphere.radius;
        camera.position.set(sphere.center.x + r * 1.5, sphere.center.y - r * 2.2, sphere.center.z + r * 1.7);
        controls.target.copy(sphere.center);
        controls.update();
        setStatus("ready");
      },
      undefined,
      () => !disposed && setStatus("error"),
    );

    let frame = 0;
    const tick = () => {
      frame = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, [url]);

  return (
    <div className="viewer" ref={host} aria-label="3D model viewer: drag to orbit, scroll to zoom">
      {status !== "ready" && <div className="viewer-status">{status === "loading" ? "Loading STL…" : "Could not load the STL."}</div>}
      <div className="viewer-hint">drag to orbit · scroll to zoom · grid = 10 mm</div>
    </div>
  );
}
