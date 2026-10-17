/* Queue PipeWire source creation on OBS's UI thread, whose GLib event loop
 * dispatches the desktop portal replies. Called by obs-display-bridge.lua. */
#include <obs.h>
#include <util/bmem.h>
#include <stdio.h>

static void create_on_ui(void *opaque)
{
    obs_data_t *request = obs_data_create_from_json(opaque);
    bfree(opaque);
    if (!request) return;
    const char *name = obs_data_get_string(request, "name");
    obs_source_t *scene_source = obs_get_source_by_name(obs_data_get_string(request, "scene"));
    obs_scene_t *scene = scene_source ? obs_scene_from_source(scene_source) : NULL;
    obs_source_t *existing = obs_get_source_by_name(name);
    bool ok = false;
    if (scene && !existing) {
        obs_data_t *settings = obs_data_get_obj(request, "settings");
        obs_source_t *source = obs_source_create("pipewire-screen-capture-source", name, settings, NULL);
        if (source) {
            obs_sceneitem_t *item = obs_scene_add(scene, source);
            if (item) {
                obs_sceneitem_set_visible(item, false);
                ok = true;
            }
            obs_source_release(source);
        }
        obs_data_release(settings);
    }
    obs_source_release(existing);
    obs_source_release(scene_source);
    obs_data_t *response = obs_data_create();
    obs_data_set_string(response, "requestId", obs_data_get_string(request, "requestId"));
    obs_data_set_bool(response, "ok", ok);
    obs_data_save_json_safe(response, "/home/knaught/.local/state/obs-display-follow/response.json", "tmp", NULL);
    obs_data_release(response);
    obs_data_release(request);
}

void knaught_queue_display_create(const char *json)
{
    obs_queue_task(OBS_TASK_UI, create_on_ui, bstrdup(json), false);
}
