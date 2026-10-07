import assert from "node:assert/strict";
import animation from "../agents/.pi/agent/extensions/calm-animation.ts";
import { macScene, renderPixels } from "../agents/.pi/agent/extensions/animation-scenes/mac-scene.ts";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Real Pi/TUI integration fixture; synthetic provider events avoid paid requests. */
export default function (pi: ExtensionAPI) {
  const handlers = new Map<string, Function>();
  const commands = new Map<string, { handler: Function }>();
  animation(new Proxy(pi, {
    get(target, key) {
      if (key === "on") return (event: string, handler: Function) => {
        handlers.set(event, handler);
        return target.on(event as never, handler as never);
      };
      if (key === "registerCommand") return (name: string, command: any) => {
        commands.set(name, command);
        return target.registerCommand(name, command);
      };
      return Reflect.get(target, key);
    },
  }));
  pi.registerCommand("test-animation", {
    description: "Exercise animation lifecycle and pixel bounds without a provider",
    handler: async (_args, ctx) => {
      let mounted = false;
      const tracked = new Proxy(ctx, {
        get(target, key) {
          if (key === "ui") return new Proxy(target.ui, {
            get(ui, field) {
              if (field === "setWidget") return (...args: any[]) => {
                mounted = args[1] !== undefined;
                return (ui.setWidget as Function)(...args);
              };
              return Reflect.get(ui, field);
            },
          });
          return Reflect.get(target, key);
        },
      });
      const emit = (name: string, event: any = {}) => handlers.get(name)?.(event, tracked);
      const delta = (type: string, text: string) => emit("message_update", {
        message: { role: "assistant" }, assistantMessageEvent: { type, delta: text },
      });
      try {
        emit("agent_start");
        assert(mounted, "animation must appear while waiting");
        await new Promise(resolve => setTimeout(resolve, 300));
        delta("thinking_delta", "Reasoning");
        assert(mounted, "reasoning is not visible response text");
        delta("toolcall_delta", "{}");
        assert(mounted, "tool arguments must not hide the animation");
        delta("text_delta", "");
        assert(mounted, "empty deltas must not hide the animation");
        delta("text_delta", "Hello");
        assert(!mounted, "first response text must immediately remove the animation");
        emit("agent_settled");
        assert(!mounted);
        emit("agent_start");
        assert(mounted, "a new request must reenable the animation");
        emit("message_end", { message: { role: "assistant", content: [{ type: "text", text: "Cached response" }] } });
        assert(!mounted, "nonstreaming response must also hide the animation");
        await commands.get("calm-animation")!.handler("mac", tracked);
        assert(mounted, "explicit previews should still work");
        delta("text_delta", "More text");
        assert(!mounted, "response text must also cancel previews");
        await commands.get("calm-animation")!.handler("off", tracked);
        emit("agent_start");
        assert(!mounted, "off must stay off");
        for (const width of [0, 1, 38, 70, 100]) for (let time = 0; time < 22000; time += 70) {
          const rows = renderPixels(macScene(width, time).pixels, text => text);
          assert.equal(rows.length, 13);
          assert(rows.every(row => row.length === width));
        }
        ctx.ui.notify("ANIMATION_TEST_PASS", "info");
      } catch (error) {
        ctx.ui.notify(`ANIMATION_TEST_FAIL: ${String(error)}`, "error");
      } finally {
        emit("session_shutdown");
      }
    },
  });
}
