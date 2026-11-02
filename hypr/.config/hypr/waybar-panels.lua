-- Migrated from waybar-panels.conf for Hyprland 0.57 (2026-11-02).
-- This Lua file is the active config; the .conf file is retained as a reference.
-- Observe mouse presses without consuming the click destined for the app.
hl.bind("mouse:272", hl.dsp.exec_cmd("~/scripts/waybar-dismiss-outside.py"), { ["non_consuming"] = true })
hl.bind("mouse:273", hl.dsp.exec_cmd("~/scripts/waybar-dismiss-outside.py"), { ["non_consuming"] = true })
hl.bind("mouse:274", hl.dsp.exec_cmd("~/scripts/waybar-dismiss-outside.py"), { ["non_consuming"] = true })

-- LocalSend dropdown, matching the Proton VPN panel.
hl.window_rule({ ["float"] = true, ["opaque"] = true, ["size"] = "480 700", ["move"] = "((monitor_w-490)) (50)", ["match"] = { ["class"] = "^(org\\.localsend\\.localsend_app)$" } })
