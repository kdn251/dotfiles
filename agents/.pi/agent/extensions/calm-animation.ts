import { readFileSync } from "node:fs";
import { join } from "node:path";
import { getAgentDir, type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { parseColor, truncateToWidth } from "@earendil-works/pi-tui";
import { macScene, renderPixels } from "./animation-scenes/mac-scene.ts";

type Mode = "mac" | "robot" | "coffee" | "cat" | "rain" | "both" | "pong" | "cpu" | "off";
const widgetKey = "calm-animation-preview";
const pixelColors = new Map<string, ReturnType<typeof parseColor>>();
function pixelColor(hex: string) {
  if (!pixelColors.has(hex)) pixelColors.set(hex, parseColor(hex));
  return pixelColors.get(hex)!;
}

function calmEnabled(): boolean {
  try {
    return JSON.parse(readFileSync(join(getAgentDir(), "calm.json"), "utf8")).enabled !== false;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "ENOENT";
  }
}

// Triangle wave: travel back and forth without a jump at the edges.
function bounce(step: number, max: number): number {
  if (max <= 0) return 0;
  const phase = step % (max * 2);
  return phase <= max ? phase : max * 2 - phase;
}

export default function (pi: ExtensionAPI) {
  let mode: Mode = "mac";
  let working = false;
  let responseStarted = false;
  let preview = false;
  let interval: ReturnType<typeof setInterval> | undefined;
  let previewTimeout: ReturnType<typeof setTimeout> | undefined;
  let mounted = false;
  let frame = 0;
  let tick = 0;
  let requestRender: (() => void) | undefined;

  function unmount(ctx: ExtensionContext) {
    if (interval) clearInterval(interval);
    interval = undefined;
    requestRender = undefined;
    if (mounted) ctx.ui.setWidget(widgetKey, undefined);
    mounted = false;
  }

  function update(ctx: ExtensionContext) {
    if (ctx.mode !== "tui") return;
    if ((!(working && !responseStarted) && !preview) || mode === "off" || !calmEnabled()) {
      unmount(ctx);
      return;
    }
    if (mounted) {
      requestRender?.();
      return;
    }
    mounted = true;
    ctx.ui.setWidget(widgetKey, (tui, theme) => {
      requestRender = () => tui.requestRender();
      return {
        invalidate() {},
        render(width: number): string[] {
          if (width <= 0) return [];
          if (mode === "mac") {
            if (width < 38) return [truncateToWidth(theme.fg("muted", "[ Macintosh · insert disk ]"), width)];
            const sceneWidth = Math.min(width, 100);
            const indent = " ".repeat(Math.floor((width - sceneWidth) / 2));
            const scene = macScene(sceneWidth, tick * 70);
            return renderPixels(scene.pixels, (text, fg, bg) =>
              theme.style(text, { ...(fg ? { fg: pixelColor(fg) } : {}), ...(bg ? { bg: pixelColor(bg) } : {}) }),
            ).map((line) => indent + line);
          }
          if (mode === "robot") {
            // Nine columns wide, four fixed rows high. Walking and turning
            // happen within that box so the editor never jumps vertically.
            const blink = frame % 47 === 31;
            const travel = Math.max(0, width - 9);
            const step = frame * 3;
            const x = bounce(step, travel);
            const rightward = travel === 0 || step % (travel * 2) < travel;
            const eyes = blink ? "─ ─" : rightward ? "• ›" : "‹ •";
            if (width < 9) return [truncateToWidth(theme.fg("accent", `[${eyes}]`), width)];
            const feet = ["   ╱ ╲   ", "   ╵ ╵   ", "   ╲ ╱   ", "   ╵ ╵   "][frame % 4]!;
            const rows = [
              "  ╭─┴─╮  ",
              `╭─┤${eyes}├─╮`,
              "╰╮╰─┬─╯╭╯",
              feet,
            ];
            return rows.map((line, row) => {
              const cells = Array<string>(width).fill(" ");
              if (row === 3) {
                for (const distance of [2, 4]) {
                  const dust = rightward ? x - distance : x + 8 + distance;
                  if (dust >= 0 && dust < width) cells[dust] = theme.fg("dim", "·");
                }
              }
              Array.from(line).forEach((character, column) => {
                cells[x + column] = theme.fg(row === 1 ? "accent" : "muted", character);
              });
              return cells.join("");
            });
          }
          if (mode === "coffee") {
            const phase = Math.floor(frame / 10) % 6;
            const steam = ["   ·   ˙", "   ˙   ˙", "   ˙   ·", "   ·   ·", "   ˙   ·", "   ˙   ˙"][phase];
            const curl = ["   )   (", "   )   )", "   (   )", "   (   (", "   (   )", "   )   )"][phase];
            const indent = " ".repeat(Math.max(0, Math.floor((width - 13) / 2)));
            const rows = [
              theme.fg("dim", steam),
              theme.fg("dim", curl),
              theme.fg("muted", "  ┌───────┐"),
              theme.fg("muted", "  │       ├─╮"),
              theme.fg("muted", "  ╰───────┴─╯"),
              theme.fg("dim", " ───────────"),
            ];
            return rows.map((line) => truncateToWidth(indent + line, width));
          }
          if (mode === "cat") {
            const phase = Math.floor(frame / 14) % 6;
            const dreams = ["", "z", "z", "z z", "z Z", "z"][phase];
            const indent = " ".repeat(Math.max(0, Math.floor((width - 16) / 2)));
            const rows = [
              "   /\\_/\\",
              `  ( -.- )  ${dreams}`,
              "   (___)~",
            ];
            return rows.map((line) => truncateToWidth(indent + theme.fg("muted", line), width));
          }
          if (mode === "rain") {
            const span = Math.min(width, 72);
            const indent = " ".repeat(Math.floor((width - span) / 2));
            const drops = Math.max(1, Math.floor(span / 12));
            const step = Math.floor(frame / 5);
            const grid = Array.from({ length: 3 }, () => Array<string>(span).fill(" "));
            for (let i = 0; i < drops; i++) {
              // Each drop falls for three beats, then rests before returning.
              // Staggered lanes avoid a synchronized curtain of rain.
              const phase = (step + i * 4) % 11;
              const x = Math.min(span - 1, Math.floor((i + 0.5) * span / drops));
              if (phase < 3) grid[phase]![x] = phase === 2 ? "·" : "╵";
            }
            return grid.map((row) => indent + theme.fg("dim", row.join("")));
          }
          if (width < 18) return [truncateToWidth(theme.fg("accent", frame % 2 ? "· working" : "• working"), width)];
          const size = Math.min(width, 48);
          const indent = " ".repeat(Math.floor((width - size) / 2));
          const dim = (text: string) => theme.fg("dim", text);
          const accent = (text: string) => theme.fg("accent", text);
          const pulse = (text: string) => theme.fg("success", text);
          const rows: string[] = [];
          if (mode === "pong" || mode === "both") {
            const inner = size - 2;
            const x = bounce(frame, inner - 1);
            const y = bounce(Math.floor(frame / 3), 2);
            rows.push(dim("PONG"));
            for (let row = 0; row < 3; row++) {
              const cells = Array.from({ length: inner }, (_, column) =>
                row === y && column === x ? pulse("●") : " ");
              const left = Math.abs(row - y) <= 1 ? accent("┃") : dim("│");
              const right = Math.abs(row - y) <= 1 ? accent("┃") : dim("│");
              rows.push(left + cells.join("") + right);
            }
          }
          if (mode === "both") rows.push("");
          if (mode === "cpu" || mode === "both") {
            rows.push(dim("CPU"));
            const leftWidth = Math.floor((size - 7) / 2);
            const rightWidth = size - 7 - leftWidth;
            const wire = (length: number, phase: number) => Array.from({ length }, (_, i) =>
              i === phase % length ? pulse("▪") : dim("─")).join("");
            rows.push(" ".repeat(leftWidth) + accent("┌─────┐"));
            rows.push(wire(leftWidth, frame) + accent("┤ CPU ├") + wire(rightWidth, frame + 3));
            rows.push(" ".repeat(leftWidth) + accent("└─────┘"));
          }
          return rows.map((line) => truncateToWidth(indent + line, width));
        },
      };
    });
    interval = setInterval(() => {
      tick++;
      if (tick % 2 === 0) frame++;
      if (mode === "mac") {
        requestRender?.();
        return;
      }
      const cadence = mode === "coffee" ? 10 : mode === "cat" ? 14 : mode === "rain" ? 5 : 1;
      if (tick % 2 === 0 && frame % cadence === 0) requestRender?.();
    }, 70);
  }

  pi.on("agent_start", (_event, ctx) => {
    working = true;
    responseStarted = false;
    update(ctx);
  });

  const hideForResponse = (ctx: ExtensionContext) => {
    responseStarted = true;
    preview = false;
    if (previewTimeout) clearTimeout(previewTimeout);
    previewTimeout = undefined;
    unmount(ctx);
  };
  pi.on("message_update", (event, ctx) => {
    // Reasoning and tool-argument deltas are not visible response text.
    const delta = event.assistantMessageEvent;
    if (delta.type === "text_delta" && delta.delta.length > 0) hideForResponse(ctx);
  });
  pi.on("message_end", (event, ctx) => {
    // Also handle providers that deliver text without intermediate deltas.
    if (event.message.role === "assistant" && event.message.content.some(
      (block) => block.type === "text" && block.text.length > 0,
    )) hideForResponse(ctx);
  });
  pi.on("agent_settled", (_event, ctx) => {
    working = false;
    update(ctx);
  });
  pi.on("session_shutdown", (_event, ctx) => {
    if (previewTimeout) clearTimeout(previewTimeout);
    previewTimeout = undefined;
    working = false;
    responseStarted = false;
    preview = false;
    unmount(ctx);
  });

  pi.registerCommand("calm-animation", {
    description: "Preview mac, robot, coffee, cat, rain, pong, cpu, or both for 20 seconds; off disables animation until reload",
    handler: async (args, ctx) => {
      if (ctx.mode !== "tui") return;
      const choice = args.trim().toLowerCase() || "mac";
      if (!["mac", "robot", "coffee", "cat", "rain", "both", "pong", "cpu", "off"].includes(choice)) {
        ctx.ui.notify("Usage: /calm-animation [mac|robot|coffee|cat|rain|both|pong|cpu|off]", "warning");
        return;
      }
      if (previewTimeout) clearTimeout(previewTimeout);
      previewTimeout = undefined;
      mode = choice as Mode;
      frame = 0;
      tick = 0;
      preview = mode !== "off";
      if (preview && !calmEnabled()) {
        preview = false;
        ctx.ui.notify("Enable Calm first with /calm on.", "info");
      }
      if (preview) previewTimeout = setTimeout(() => {
        preview = false;
        previewTimeout = undefined;
        update(ctx);
      }, 20_000);
      update(ctx);
    },
  });
}
