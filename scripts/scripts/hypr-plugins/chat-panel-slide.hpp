#pragma once
#include <hyprland/src/animation/WorkspaceAnimationController.hpp>
#include <hyprland/src/desktop/view/window/WindowEffectsController.hpp>
#include <hyprland/src/render/transformer/TransformerList.hpp>

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cmath>

namespace ChatSlide {
class Clip : public Render::IWindowTransformer {
  public:
    bool enabled = true;
    CBox bounds;
    explicit Clip(CBox box) : bounds(box) {}
    bool active() const override { return enabled; }
    bool allocatesOutputBuffer() const override { return false; }
    Render::SWindowTransformBuffer transform(Render::CRenderContext&, const Render::SWindowTransformBuffer& in,
                                              const Render::SWindowTransformContext&) override { return in; }
    void preWindowRender(Render::CRenderContext&, CSurfacePassElement::SRenderData* data) override {
        data->clipBox = bounds;
    }
};
static CHyprSignalListener specialListener, frameListener;
static PHLWINDOWREF pane, player;
static PHLWORKSPACEREF workspace;
static int endpoint = -1;
static bool showing = false;
static double width = 1, ratio = 0, last = -1;
static void sendMargin(double value) {
    if (endpoint < 0 || std::abs(value-last)<.00001) return;
    const auto message=std::string("{\"command\":[\"set_property\",\"video-margin-ratio-right\",")+std::to_string(value)+"]}\n";
    if (::send(endpoint,message.data(),message.size(),MSG_DONTWAIT|MSG_NOSIGNAL)==static_cast<ssize_t>(message.size())) last=value;
    // Discard command acknowledgements without ever blocking the compositor.
    char buffer[4096]; while (::recv(endpoint,buffer,sizeof(buffer),MSG_DONTWAIT)>0) {}
}
static void cleanup() {
    if (auto window=pane.lock()) {
        auto& list=window->effects().transformers();
        if (auto clip=list->get<Clip>()) clip->enabled=false;
        list->removeInactive();
    }
    if (endpoint>=0) ::close(endpoint);
    endpoint=-1;pane.reset();player.reset();workspace.reset();last=-1;
}
static void start() {
    if (auto runtime=std::getenv("XDG_RUNTIME_DIR")) std::ofstream(std::string(runtime)+"/media-chat-slide-enabled") << "1\n";
    specialListener=Event::bus()->m_events.workspace.specialActive.listen([](PHLWORKSPACE opened,PHLMONITOR monitor) {
        if (opened && opened->addressableName()!="special:chatterino_chat") return;
        PHLWINDOW chat, video;
        for (const auto& window:Desktop::windowState()->windows()) {
            if (!window->mapped() || window->m_monitor!=monitor) continue;
            if (window->m_workspace && window->m_workspace->addressableName()=="special:chatterino_chat") chat=window;
            if (window->metadata().appID()=="mpv" && window->m_workspace==monitor->m_activeWorkspace) video=window;
        }
        if (!chat || !video) return;
        const auto ws=chat->m_workspace;
        // Workspace navigation retains the existing instant-hide behavior.
        if (opened && opened!=ws) return;
        cleanup();pane=chat;player=video;workspace=ws;showing=bool(opened);
        width=chat->size(Desktop::View::IGeometric::GEOMETRIC_GOAL).x;
        const bool theater=Fullscreen::controller()->isFullscreen(video);
        const bool fromRight=theater || chat->position(Desktop::View::IGeometric::GEOMETRIC_GOAL).x < video->position(Desktop::View::IGeometric::GEOMETRIC_GOAL).x;
        const double offset=fromRight?width:-width;
        Animation::Workspace::startAnimation(ws,showing?Animation::Workspace::ANIMATION_TYPE_IN:Animation::Workspace::ANIMATION_TYPE_OUT,
                                             showing?fromRight:!fromRight,false,"slide");
        // Override the cached workspace rule with exact pane-width endpoints.
        if (showing) { ws->m_renderOffset->setValueAndWarp(Vector2D{offset,0.0}); *ws->m_renderOffset=Vector2D{}; }
        else { ws->m_renderOffset->setValueAndWarp(Vector2D{}); *ws->m_renderOffset=Vector2D{offset,0.0}; }
        ws->m_alpha->setValueAndWarp(1.f);
        CBox bounds{chat->position(Desktop::View::IGeometric::GEOMETRIC_GOAL)-monitor->m_position,
                    chat->size(Desktop::View::IGeometric::GEOMETRIC_GOAL)};
        chat->effects().transformers()->emplace<Clip>(bounds.scale(monitor->m_scale).round());
        if (!theater) return;
        try {
            const auto runtime=std::getenv("XDG_RUNTIME_DIR");
            if (!runtime) return;
            std::ifstream input(std::string(runtime)+"/media-chat-slide-socket");
            std::string path;std::getline(input,path);
            if (path.empty()) return;
            sockaddr_un address{};address.sun_family=AF_UNIX;
            if (path.size()>=sizeof(address.sun_path)) return;
            std::copy(path.begin(),path.end(),address.sun_path);
            endpoint=::socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
            if (endpoint<0 || ::connect(endpoint,reinterpret_cast<sockaddr*>(&address),sizeof(address))<0) {
                if(endpoint>=0)::close(endpoint);endpoint=-1;return;
            }
            ratio=width/monitor->m_size.x;
            sendMargin(showing?0:ratio);
        } catch (...) {}
    });
    frameListener=Event::bus()->m_events.render.pre.listen([](PHLMONITOR monitor) {
        const auto ws=workspace.lock(); const auto video=player.lock();
        if (!ws || ws->m_monitor!=monitor) return;
        if (video && Fullscreen::controller()->isFullscreen(video))
            sendMargin(ratio*std::clamp(1-std::abs(ws->m_renderOffset->value().x)/width,0.,1.));
        else sendMargin(0);
        if (!ws->m_renderOffset->isBeingAnimated()) {
            if (!showing) ws->m_alpha->setValueAndWarp(0.f);
            cleanup();
        }
    });
}
static void stop() { specialListener.reset();frameListener.reset();cleanup();
    if(auto runtime=std::getenv("XDG_RUNTIME_DIR")) ::unlink((std::string(runtime)+"/media-chat-slide-enabled").c_str());
}
}
