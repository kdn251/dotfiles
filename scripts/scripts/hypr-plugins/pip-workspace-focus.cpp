#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/view/window/Window.hpp>
#include <hyprland/src/workspace/HLWorkspace.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <stdexcept>
#include <fstream>
#include <cstdlib>

static CHyprSignalListener workspaceListener;
static CHyprSignalListener fullscreenListener;

static void focusOtherApp(PHLWORKSPACE workspace, Desktop::eFocusReason reason) {
    PHLWINDOW target;
    const auto& windows = Desktop::windowState()->windows();
    for (auto it = windows.rbegin(); it != windows.rend(); ++it) {
        const auto& window = *it;
        if (!window->mapped() || window->isHidden() || !window->focusAvailable() ||
            window->metadata().appID() == "mpv")
            continue;
        if (window->m_workspace == workspace) {
            target = window;
            break;
        }
    }
    Desktop::focusState()->rawWindowFocus(target, reason);
}

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
                if (workspace->numberedID().value_or(0) != workspaceID && special && special->addressableName() == "special:chatterino_chat") {
                    monitorForChat->setSpecialWorkspace(PHLWORKSPACE{});
                    // Closing a special workspace can retain its outgoing
                    // animation. It must be invisible on the destination's
                    // very first frame, not merely scheduled to fade out.
                    special->m_alpha->setValueAndWarp(0.f);
                    special->m_renderOffset->warp();
                } else if (workspace->numberedID().value_or(0) == workspaceID && !special) {
                    for (const auto& window : Desktop::windowState()->windows()) {
                        if (window->mapped() && window->m_workspace &&
                            window->m_workspace->addressableName() == "special:chatterino_chat" &&
                            (window->metadata().appID() == "com.chatterino.chatterino" || window->metadata().appID() == "newsboat-live-chat")) {
                            monitorForChat->setSpecialWorkspace(window->m_workspace);
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
            !active || active->metadata().appID() != "mpv" || active->m_monitor != monitor)
            return;

        // Workspace entry must never select MPV, even if it was the last
        // focused window there. Prefer an eligible normal app on that workspace.
        // Raw focus does not tear down a fullscreen player behind the sidebar.
        focusOtherApp(workspace, Desktop::FOCUS_REASON_WORKSPACE_CHANGE);
    });
    fullscreenListener = Event::bus()->m_events.window.fullscreen.listen([](PHLWINDOW window) {
        if (!window || window->metadata().appID() != "mpv" ||
            Fullscreen::controller()->isFullscreen(window) || Desktop::focusState()->window() != window)
            return;
        const auto monitor = Desktop::focusState()->monitor();
        if (monitor && monitor->m_activeWorkspace)
            focusOtherApp(monitor->m_activeWorkspace, Desktop::FOCUS_REASON_OTHER);
    });
    return {"pip-workspace-focus", "Keep MPV unfocused on workspace entry", "local", "1.3"};
}

APICALL EXPORT void PLUGIN_EXIT() {
    workspaceListener.reset();
    fullscreenListener.reset();
}
