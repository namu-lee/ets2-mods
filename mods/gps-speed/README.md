# Dashboard GPS Speed

Adds a speed limit sign and current speed to the dashboard GPS in all SCS trucks and coaches.

## Development

### Rebuild screenshot preview

The script builds [preview.jpg](preview.jpg) at 1920×1080 and keeps it under 1 MB for Steam Workshop. On `main`, [Actions](https://github.com/namu-lee/ets2-mods/actions/workflows/preview.yml) rebuilds and commits it when its inputs change.

```powershell
python -m pip install -r requirements.txt
python .\mods\gps-speed\build_preview.py
```

### Indicator size and position

#### 1. Size

Measure at native 2560×1440 using each vehicle’s default FOV and default left-hand-drive cab view (`1`). Aim for **17–18 px for the limit and 16 px for current speed**. Reuse those scales on right-hand-drive cabs.

Set `xscale = yscale` for current speed and `xscale = 0.8 × yscale` for the limit so three digits fit inside the ring. [Text templates](src/ui/template/dashboard_text.gps_speed.sii)

**Exception.** Use the largest size that fits when the target size would clip or overlap controls.

- Volvo 9700 (11–12 px limit, 11 px current speed)

#### 2. Position

Stack the displays at the map’s upper left, just below any controls in that corner. Check both steering sides for overlap and clipping.

**Exception.** Center the stack vertically in the gap when the left column has controls above and below it.

- Scania R/S Smart Dash (10.1″ and 12.9″)
- Volvo FH 2021
- Volvo 9700
