#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <stdexcept>

static CHyprSignalListener workspaceListener;

APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("PiP focus: rebuild against the running Hyprland version");

    workspaceListener = Event::bus()->m_events.workspace.active.listen([](PHLWORKSPACE workspace) {
        const auto focus = Desktop::focusState();
        const auto active = focus->window();
        const auto monitor = focus->monitor();
        if (!workspace || !monitor || monitor->m_activeWorkspace != workspace ||
            monitor->m_activeSpecialWorkspace || !active || active->m_class != "mpv" ||
            !active->m_pinned || active->m_monitor != monitor)
            return;

        // Ignore pinned MPV overlays when deciding whether the destination is empty.
        // Other floating windows and other pinned apps are real focus targets.
        for (const auto& window : Desktop::windowState()->windows()) {
            if (!window->m_isMapped || window->isHidden())
                continue;
            if (window->m_pinned && window->m_class == "mpv")
                continue;
            if (window->m_workspace == workspace ||
                (window->m_pinned && window->m_monitor == monitor))
                return;
        }
        focus->fullWindowFocus(nullptr, Desktop::FOCUS_REASON_WORKSPACE_CHANGE);
    });
    return {"pip-workspace-focus", "Keep pinned MPV unfocused on empty workspace entry", "local", "1.0"};
}

APICALL EXPORT void PLUGIN_EXIT() {
    workspaceListener.reset();
}
