#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <stdexcept>
#include <fstream>
#include <cstdlib>

static CHyprSignalListener workspaceListener;

APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("PiP focus: rebuild against the running Hyprland version");

    workspaceListener = Event::bus()->m_events.workspace.active.listen([](PHLWORKSPACE workspace) {
        const auto focus = Desktop::focusState();
        // Hide/show fullscreen chat in the workspace transaction itself,
        // before another frame renders. The Python controller owns this file.
        const auto monitorForChat = workspace ? workspace->m_monitor.lock() : PHLMONITOR{};
        const auto runtime = std::getenv("XDG_RUNTIME_DIR");
        if (runtime && workspace && monitorForChat && monitorForChat->m_activeWorkspace == workspace) {
            std::ifstream owner(std::string(runtime) + "/media-chat-workspace-owner");
            int64_t workspaceID = 0, monitorID = -1, specialID = 0;
            if ((owner >> workspaceID >> monitorID >> specialID) &&
                monitorForChat->m_id == monitorID && specialID < 0) {
                const auto special = monitorForChat->m_activeSpecialWorkspace;
                if (workspace->m_id != workspaceID && special && special->m_id == specialID) {
                    monitorForChat->setSpecialWorkspace(PHLWORKSPACE{});
                    // Closing a special workspace can retain its outgoing
                    // animation. It must be invisible on the destination's
                    // very first frame, not merely scheduled to fade out.
                    special->m_alpha->setValueAndWarp(0.f);
                    special->m_renderOffset->warp();
                } else if (workspace->m_id == workspaceID && !special) {
                    for (const auto& window : Desktop::windowState()->windows()) {
                        if (window->m_isMapped && window->m_workspace &&
                            window->m_workspace->m_id == specialID &&
                            (window->m_class == "com.chatterino.chatterino" || window->m_class == "newsboat-live-chat")) {
                            monitorForChat->setSpecialWorkspace(specialID);
                            window->m_workspace->m_alpha->setValueAndWarp(1.f);
                            window->m_workspace->m_renderOffset->setValueAndWarp(Vector2D{});
                            break;
                        }
                    }
                }
            }
        }
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
    return {"pip-workspace-focus", "Keep pinned MPV unfocused on empty workspace entry", "local", "1.1"};
}

APICALL EXPORT void PLUGIN_EXIT() {
    workspaceListener.reset();
}
