# Dashboard GPS Speed & Forward View

See the [mod description](description.md) for features and compatibility.

From the repository root, install the [shared build dependencies](../../README.md#local-builds) and run:

```powershell
python .\scripts\build.py .\mods\gps-speed-view
```

The package is written to `build/gps-speed-view/ets2-gps-speed-view.scs`. The build takes the layouts and vehicle definitions from the `source_mod` named in [mod.json](mod.json). This edition lists `view` under `features`, so the builder runs the source mod's [shared/apply_features.py](../gps-speed/shared/apply_features.py) to apply it. Edit the shared layouts in `gps-speed/src`.

- Edit `map_3d_camera_pitch` directly in [map_data.sii](../gps-speed/shared/view/map_data.sii). The dashboard uses 65% of this value, so `61.538464` gives a 40-degree dashboard angle. The build copies the file to `def/map_data.sii`.
- Edit `marker_height` in [gps-view.json](../gps-speed/shared/view/gps-view.json). The build adjusts the inherited GPS layouts to place the marker this fraction of the way up from the bottom of the map. Use `0.20` for 20%.
