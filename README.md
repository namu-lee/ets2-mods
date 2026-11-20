# ETS2 Mods

Mods for Euro Truck Simulator 2.

Original contributions are licensed under the GPLv3. See [LICENSE](LICENSE).

- [Dashboard GPS Speed](mods/gps-speed/) · [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3841119859)
- [Dashboard GPS Speed: Enhanced View](mods/gps-speed-view/)
- [HUD Side Swap](mods/hud-side-swap/) · [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3841187300)
- [No Minimap](mods/no-minimap/) · [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3841426514)

## Local builds

Run these commands from the repository root with Python 3.12.

```powershell
python -m pip install -r requirements.txt
python .\scripts\build.py .\mods\MOD_NAME
```

Each mod has a `src\` directory with `manifest.sii` and a `mod.json` with its `.scs` filename and optional Workshop item ID. Put `icon.jpg` beside `mod.json` to generate the in-game icon for the Workshop package. The `.scs` and Workshop ZIP go into `build\<mod-name>\` at the repository root.

A mod can declare `source_mod` in `mod.json` to reuse another mod's source. The builder copies the source mod's `src` into a temporary directory and overlays the current mod's `src` files.

When the current mod declares a nonempty `features` list, the local and Workshop builders run `shared/apply_features.py` from the source mod, or from the current mod if it has no `source_mod`. The script runs with the current mod's directory as its working directory and gets the absolute path to the staged `src` as its sole argument. It reads the current mod's `features` and applies them in order.

Edit the mod's `description.md` to update its in-game and Workshop descriptions. Both package builds use the Pandoc bundled with `pypandoc-binary` to generate the plain-text file specified by `description_file` in `manifest.sii`. In-game descriptions keep the link text. The Workshop upload converts the same Markdown to Steam BBCode with clickable links.

## Releases

Pushes and pull requests to `main` build the affected mods. A change to the common build scripts rebuilds all mods.

Update the mod's `package_version` in `src\manifest.sii`, push the release commit to `main`, then tag it using the mod directory name and version.

```powershell
git tag -a no-minimap/v0.0.2 -m "Adjust the Route Advisor layout"
git push origin refs/tags/no-minimap/v0.0.2
```

GitHub Actions attaches that mod's `.scs` to a release titled after the tag. The tag message becomes the release body and the Steam Workshop change note. A mod with a `workshop_item_id` also updates that item using its current visibility. Run **Release a mod** manually with a mod directory name to build its Workshop ZIP artifact.

## Steam Workshop setup

1. For the first upload, build the Workshop ZIP locally and use its extracted `workshop\` directory as **Mod data**. Select the mod's `icon.jpg` as the preview. [SCS Workshop upload guide](https://modding.scssoft.com/wiki/Tutorials/SCS_Workshop_Uploader/How_to_upload_new_mod%3F)
2. Add the resulting item ID as a string in the mod's `mod.json`. Use `null` until the item has been created.
3. Create the `steam-workshop` environment. If it has deployment rules, allow the per-mod release tags. Store `STEAM_USERNAME` and `STEAM_CONFIG_VDF_B64` as environment secrets for the account that can update the items. [GitHub Actions environment secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets#creating-secrets-for-an-environment)
4. To generate `STEAM_CONFIG_VDF_B64`, sign in to SteamCMD locally with the command below. Complete Steam Guard and enter `quit`. Verify cached login, then Base64-encode the resulting `config.vdf`. [Steamworks CI login guide](https://partner.steamgames.com/doc/sdk/uploading)

   ```powershell
   .\steamcmd.exe +login YOUR_STEAM_USERNAME
   .\steamcmd.exe +login YOUR_STEAM_USERNAME +quit
   $config = (Resolve-Path -LiteralPath '.\config\config.vdf').ProviderPath
   Set-Clipboard -Value ([Convert]::ToBase64String([IO.File]::ReadAllBytes($config)))
   ```

   Save the clipboard value as `STEAM_CONFIG_VDF_B64`.
