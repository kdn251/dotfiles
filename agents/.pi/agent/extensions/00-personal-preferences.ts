import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Portable question-layout default, independent of the launching shell. */
export default function (_pi: ExtensionAPI) {
  // An explicit shell preference still takes precedence.
  process.env.PI_ASK_USER_DISPLAY_MODE ??= "inline";
}
