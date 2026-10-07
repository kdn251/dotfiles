import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getAgentDir, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Text, type Component } from "@earendil-works/pi-tui";

/** Lightweight conversation-focused display. Never replaces tool execution. */
export default function (pi: ExtensionAPI) {
  const preference = join(getAgentDir(), "calm.json");
  let enabled = true;
  try {
    enabled = JSON.parse(readFileSync(preference, "utf8")).enabled !== false;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      // Fail visibly rather than hiding activity with a malformed preference.
      enabled = false;
      console.error("Calm: could not read calm.json; leaving tool activity visible.");
    }
  }

  pi.registerCommand("calm", {
    description: "Toggle hidden tool activity, or use /calm on or /calm off",
    handler: async (args, ctx) => {
      const mode = args.trim().toLowerCase();
      if (mode && mode !== "on" && mode !== "off") {
        ctx.ui.notify("Usage: /calm [on|off]", "warning");
        return;
      }
      const next = mode ? mode === "on" : !enabled;
      mkdirSync(getAgentDir(), { recursive: true });
      const temporary = `${preference}.${process.pid}.tmp`;
      writeFileSync(temporary, `${JSON.stringify({ enabled: next }, null, 2)}\n`, { mode: 0o600 });
      renameSync(temporary, preference);
      // Reload rebuilds existing rows, restoring original renderers when off.
      await ctx.reload();
    },
  });

  if (!enabled) return;
  const empty: Component = { render: () => [], invalidate() {} };

  pi.registerToolRenderer((name, next) => {
    // Keep interactive decisions and their answers visible.
    if (name === "ask_user") return next();
    const original = next();
    return {
      renderShell: "self",
      renderCall(args, theme, context) {
        if (!context.isError) return empty;
        return original?.renderCall?.(args, theme, context)
          ?? new Text(theme.fg("error", `${name} failed`), 0, 0);
      },
      renderResult(result, options, theme, context) {
        if (!context.isError) return empty;
        return original?.renderResult?.(result, options, theme, context)
          ?? new Text(theme.fg("error", result.content
            .filter((block) => block.type === "text")
            .map((block) => block.text).join("\n") || `${name} failed`), 0, 0);
      },
    };
  });

  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode === "tui") ctx.ui.setHiddenThinkingLabel("");
  });
}
