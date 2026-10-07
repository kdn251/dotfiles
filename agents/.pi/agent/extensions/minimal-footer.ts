import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

/** Compact footer only; leave the editor and built-in working indicator intact. */
export default function (pi: ExtensionAPI) {
  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    ctx.ui.setFooter((_tui, theme) => ({
      invalidate() {},
      render(width: number): string[] {
        if (width <= 0) return [];
        const percent = ctx.getContextUsage()?.percent;
        const context = `context ${percent == null ? "?" : `${Math.round(percent)}%`}`;
        let cost = 0;
        for (const entry of ctx.sessionManager.getBranch()) {
          if (entry.type === "message" && entry.message.role === "assistant") {
            cost += entry.message.usage?.cost?.total ?? 0;
          }
        }
        const details = `${ctx.model?.id ?? "no model"} · ${pi.getThinkingLevel()} · $${cost.toFixed(2)}`;
        const color = percent != null && percent >= 90 ? "error" : percent != null && percent >= 75 ? "warning" : "dim";
        if (width <= visibleWidth(context) + 4) {
          return [truncateToWidth(theme.fg(color, context), width)];
        }
        const left = truncateToWidth(details, width - visibleWidth(context) - 2);
        const gap = " ".repeat(Math.max(2, width - visibleWidth(left) - visibleWidth(context)));
        return [theme.fg("dim", left) + gap + theme.fg(color, context)];
      },
    }));
  });

  pi.registerCommand("default-footer", {
    description: "Restore Pi's default footer until the next reload",
    handler: async (_args, ctx) => {
      if (ctx.mode === "tui") ctx.ui.setFooter(undefined);
    },
  });
}
