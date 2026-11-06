#pragma once
#include <hyprland/src/desktop/view/LayerSurface.hpp>
#include <hyprland/src/desktop/state/FadingOutState.hpp>
#include <hyprland/src/desktop/state/LayerFadeout.hpp>

// Reserve only the part of the sidebar currently visible, not its final width.
namespace SidebarSlide {
static CHyprSignalListener opened, closed, frame;
static PHLLSREF pane;
static PHLMONITORREF screen;
static int endpoint=-1;
static double last=-1, closingWidth=0;
static std::string socketPath;
static std::vector<SP<Desktop::IFadeout>> previousFadeouts;
static SP<Desktop::IFadeout> outgoing;
static bool awaitingFadeout=false;
static void disconnect() { if(endpoint>=0)::close(endpoint);endpoint=-1;last=-1; }
static void send(double value) {
    if(endpoint<0 || std::abs(value-last)<.00001)return;
    auto message=std::string("{\"command\":[\"set_property\",\"video-margin-ratio-left\",")+std::to_string(value)+"]}\n";
    if(::send(endpoint,message.data(),message.size(),MSG_DONTWAIT|MSG_NOSIGNAL)==static_cast<ssize_t>(message.size()))last=value;
    char buffer[4096];while(::recv(endpoint,buffer,sizeof(buffer),MSG_DONTWAIT)>0){}
}
static void connectPlayer() {
    const auto runtime=std::getenv("XDG_RUNTIME_DIR");if(!runtime)return;
    std::ifstream input(std::string(runtime)+"/media-sidebar-slide-socket");
    std::string path;std::getline(input,path);
    if(path==socketPath && endpoint>=0)return;
    disconnect();socketPath=path;
    sockaddr_un address{};address.sun_family=AF_UNIX;
    if(path.empty() || path.size()>=sizeof(address.sun_path))return;
    std::copy(path.begin(),path.end(),address.sun_path);
    endpoint=::socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
    if(endpoint>=0 && ::connect(endpoint,reinterpret_cast<sockaddr*>(&address),sizeof(address))<0)disconnect();
}
static void start() {
    if(auto runtime=std::getenv("XDG_RUNTIME_DIR"))std::ofstream(std::string(runtime)+"/media-sidebar-slide-enabled")<<"1\n";
    opened=Event::bus()->m_events.layer.opened.listen([](PHLLS layer){
        if(layer->m_namespace!="stream-sidebar")return;
        pane=layer;screen=layer->m_monitor;outgoing.reset();awaitingFadeout=false;
        connectPlayer();
        // Slide an opaque panel; independently fading it exposes the black
        // video margin through its background even with matching geometry.
        layer->alpha().get(Desktop::View::LS_ALPHA_FADE)->setValueAndWarp(1.f);
    });
    closed=Event::bus()->m_events.layer.closed.listen([](PHLLS layer){
        if(layer->m_namespace!="stream-sidebar")return;
        closingWidth=layer->size(Desktop::View::IGeometric::GEOMETRIC_CURRENT).x;
        previousFadeouts=Desktop::fadingOutState()->fadeouts();
        awaitingFadeout=true;pane.reset();
    });
    frame=Event::bus()->m_events.render.pre.listen([](PHLMONITOR monitor){
        if(screen.lock()!=monitor)return;
        if(auto layer=pane.lock();layer && layer->mapped()) {
            connectPlayer();
            const auto box=layer->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
            const double visible=std::clamp(box.x+box.w-monitor->m_position.x,0.,box.w);
            send(visible/monitor->m_size.x);
            return;
        }
        if(awaitingFadeout) {
            for(const auto& fade:Desktop::fadingOutState()->fadeouts())
                if(fade->monitor().lock()==monitor && dynamic_cast<Desktop::CLayerFadeout*>(fade.get()) &&
                   std::find(previousFadeouts.begin(),previousFadeouts.end(),fade)==previousFadeouts.end()) {outgoing=fade;break;}
            previousFadeouts.clear();awaitingFadeout=false;
        }
        if(outgoing && !outgoing->done())send(closingWidth*outgoing->alpha()/monitor->m_size.x);
        else {send(0);outgoing.reset();screen.reset();disconnect();}
    });
}
static void stop() {
    opened.reset();closed.reset();frame.reset();disconnect();pane.reset();screen.reset();outgoing.reset();previousFadeouts.clear();
    if(auto runtime=std::getenv("XDG_RUNTIME_DIR"))::unlink((std::string(runtime)+"/media-sidebar-slide-enabled").c_str());
}
}
