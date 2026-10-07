// Run with Node >= 22, using native TypeScript stripping. No npm dependencies.
import { macScene } from './mac-scene.ts';
import { writeFileSync } from 'node:fs';
const frames = [];
for (let ms = 0; ms <= 6000; ms += 70) {
  // Keep the original pixels, easing and phase logic; compress only the timeline.
  const sceneMs = ms < 2700 ? 3000 + ms * (4500 / 2700) : 7500 + (ms - 2700);
  frames.push(macScene(38, sceneMs));
}
writeFileSync(new URL('./frames.json', import.meta.url), JSON.stringify({ interval: 70, frames }));
console.log(`Generated ${frames.length} original-art frames`);
