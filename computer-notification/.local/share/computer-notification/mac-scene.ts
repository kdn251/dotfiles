/** Pixel-art Macintosh delivery scene. Each terminal row holds two pixel rows. */
export type Pixel = string | null;
export type MacScene = { pixels: Pixel[][]; phase: "travel" | "insert" | "read" | "happy" };
const c = {
  outline: "#756e62", shadow: "#a69a81", case: "#cfc3a6", light: "#eadfc4",
  bezel: "#948c76", glass: "#152d29", screen: "#254c40", phosphor: "#a6d8a4",
  disk: "#466483", diskLight: "#7594af", diskDark: "#263e54", metal: "#c3cbd0",
  label: "#e6dcc5", ink: "#8e7c67", ground: "#454d50", glow: "#c7e9ad",
};
const ease = (t: number) => t * t * (3 - 2 * t);

export function macScene(width: number, elapsedMs: number): MacScene {
  const w = Math.max(0, Math.floor(width));
  const pixels: Pixel[][] = Array.from({ length: 26 }, () => Array<Pixel>(w).fill(null));
  const rect = (x: number, y: number, rw: number, rh: number, color: Pixel) => {
    for (let py = Math.max(0, y); py < Math.min(26, y + rh); py++) {
      for (let px = Math.max(0, x); px < Math.min(w, x + rw); px++) pixels[py]![px] = color;
    }
  };
  const phaseMs = Math.max(0, elapsedMs) % 11_000;
  const phase = phaseMs < 4500 ? "travel" : phaseMs < 6000 ? "insert" : phaseMs < 7500 ? "read" : "happy";
  if (w < 38) return { pixels, phase };
  const mx = w - 29;
  const my = 1;
  // Ground and cast shadow ground the object without an enclosing UI box.
  rect(1, 25, w - 2, 1, c.ground);
  rect(mx - 2, 24, 28, 1, c.ground);
  // Beveled beige enclosure: broad face, lit top/left, shadowed right edge.
  rect(mx + 2, my, 20, 1, c.outline);
  rect(mx + 1, my + 1, 23, 22, c.outline);
  rect(mx + 2, my + 1, 20, 21, c.case);
  rect(mx + 2, my + 1, 20, 1, c.light);
  rect(mx + 2, my + 2, 1, 19, c.light);
  rect(mx + 22, my + 2, 1, 20, c.shadow);
  rect(mx + 3, my + 21, 19, 1, c.shadow);
  // CRT recess, dark glass, green inner screen, and a restrained reflection.
  rect(mx + 4, my + 3, 16, 12, c.bezel);
  rect(mx + 5, my + 4, 14, 10, c.glass);
  rect(mx + 6, my + 5, 12, 8, c.screen);
  rect(mx + 6, my + 5, 5, 1, "#426556");
  rect(mx + 6, my + 6, 1, 2, "#365a4a");
  // A centered face after delivery; disk-reading raster beforehand.
  if (phase === "happy") {
    rect(mx + 8, my + 7, 1, 2, c.phosphor);
    rect(mx + 15, my + 7, 1, 2, c.phosphor);
    rect(mx + 9, my + 10, 1, 1, c.phosphor);
    rect(mx + 14, my + 10, 1, 1, c.phosphor);
    rect(mx + 10, my + 11, 4, 1, c.phosphor);
  } else if (phase === "read") {
    const progress = Math.min(8, Math.floor((phaseMs - 6000) / 180));
    rect(mx + 8, my + 8, 8, 3, c.glass);
    rect(mx + 8, my + 9, progress, 1, c.phosphor);
  } else {
    rect(mx + 8, my + 10, 3, 1, c.phosphor);
  }
  // Disk slot, activity LED, speaker vents, badge, and separate feet.
  rect(mx + 9, my + 17, 10, 1, c.outline);
  rect(mx + 9, my + 18, 10, 1, c.glass);
  rect(mx + 9, my + 19, 10, 1, c.light);
  rect(mx + 20, my + 18, 1, 1, phase === "read" ? c.glow : c.shadow);
  for (let x = 0; x < 4; x++) rect(mx + 4 + x, my + 17, 1, 1, x % 2 ? c.shadow : c.outline);
  rect(mx + 4, my + 19, 2, 1, c.ink);
  rect(mx + 4, my + 23, 4, 1, c.shadow);
  rect(mx + 17, my + 23, 4, 1, c.shadow);

  // A 12x12 disk travels to the drive, then rotates edge-on and slides in.
  if (phase === "travel" || phase === "insert") {
    const disk: Pixel[][] = Array.from({ length: 12 }, () => Array<Pixel>(12).fill(c.disk));
    const paint = (x: number, y: number, rw: number, rh: number, color: Pixel) => {
      for (let py = y; py < y + rh; py++) for (let px = x; px < x + rw; px++) disk[py]![px] = color;
    };
    paint(0, 0, 12, 1, c.diskDark); paint(0, 0, 1, 12, c.diskLight);
    paint(11, 0, 1, 12, c.diskDark); paint(0, 11, 12, 1, c.diskDark);
    paint(3, 0, 6, 4, c.metal); paint(6, 1, 2, 2, c.diskDark);
    paint(2, 6, 8, 5, c.label); paint(3, 7, 6, 1, c.ink);
    paint(3, 9, 4, 1, c.ink); paint(1, 10, 1, 1, c.diskDark);
    const t = Math.min(1, phaseMs / 4500);
    const targetX = mx + 8;
    const dx = Math.round(-12 + (targetX + 12) * ease(t));
    const bob = Math.sin(t * Math.PI * 2) * Math.sin(t * Math.PI);
    const insert = Math.max(0, (phaseMs - 4500) / 1500);
    const dh = Math.max(1, Math.round(12 * (1 - ease(Math.min(1, insert * 1.5)))));
    const dw = insert > 0.65 ? Math.max(0, Math.round(12 * (1 - (insert - 0.65) / 0.35))) : 12;
    const dy = Math.round(my + 18 - (dh - 1) / 2 + bob);
    for (let y = 0; y < dh; y++) {
      for (let x = 0; x < dw; x++) {
        rect(dx + x, dy + y, 1, 1, disk[Math.min(11, Math.floor(y * 12 / dh))]![x]!);
      }
    }
  }
  return { pixels, phase };
}

export function renderPixels(pixels: Pixel[][], style: (text: string, fg?: string, bg?: string) => string): string[] {
  const rows: string[] = [];
  for (let y = 0; y < pixels.length; y += 2) {
    let line = "";
    for (let x = 0; x < (pixels[y]?.length ?? 0); x++) {
      const upper = pixels[y]![x];
      const lower = pixels[y + 1]?.[x];
      line += upper && lower ? style("▀", upper, lower)
        : upper ? style("▀", upper)
        : lower ? style("▄", lower) : " ";
    }
    rows.push(line);
  }
  return rows;
}
