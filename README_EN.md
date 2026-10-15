<div align="center">
  
### [🇨🇳 简体中文](README.md) | [🇺🇸 English](README_EN.md)

</div>

# ⚠️ This is a Fork Maintained Version

> **This repository is forked from [weilin9999/WeiLin-ComfyUI-prompt-all-in-one](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one)**
>
> **The original author archived the repo on 2025-03-24. This fork only does bug fixes and tag library expansion — no new features are added.**
>
> For the original author's new node, visit: [WeiLin-Comfyui-Tools](https://github.com/weilin9999/WeiLin-Comfyui-Tools)

---

## Changes vs the Original

### Tag Library Expansion
- Total tags expanded from ~3,600 to **~5,800+** (~2,200 new tags added)
- 14 top-level categories, 135+ sub-categories
- **100% translation rate** (all tags have Chinese display names)
- All tag names follow `^[a-z][a-z0-9_]*$` format

### Bug Fixes
- **PromptUI value clearing bug**: Fixed input content being cleared after multiple button clicks (`dispatchEvent(new Event('input', {bubbles: true}))`)
- **Python 3.13 compatibility**: Fixed `pkg_resources.ImpImporter` crash under embedded Python 3.13 (upgraded setuptools to 81.0.0)
- **YAML blank-line fix**: The frontend custom YAML parser relies on blank lines to separate sub-categories — restored 139 missing blank lines

### Performance Overhaul (2026-10-15)

Three-layer rework (P0 startup / P1 runtime / P2 transport) targeting the root cause: slow sync calls blocking ComfyUI's single event loop. All blocking IO moved to worker threads, caching added, responses now gzip + ETag. Measured locally (ComfyUI 0.40 / RTX 3080):

| Metric | Before | After |
| --- | --- | --- |
| Plugin import at startup | 7.1 s | 0.3–0.5 s (≈96% less) |
| Tag library read (228 KB) | 619 ms per request | 3.2 ms cold / 0.01 ms hot |
| Edit one tag | 966 ms, freezes whole UI | 47–477 ms, never freezes UI |
| Hash of largest Lora (2250 MB) | full-file sha256, 3.6–7.3 s | sampled fingerprint 7–40 ms, 0.2 ms in-process reuse |
| Lora panel API (151 items) | per-file full hash, blocks UI | 137–181 ms; response 139 KB → 8 KB gzip |
| Front-end JS bundle | 736 KB plaintext, re-sent on every reload | 228 KB gzip, HTTP 304 on revisit |
| get_config | 415 KB | 67 KB gzip |
| Autocomplete dict (1.78 MB) | `no-store`, re-downloaded every time | ETag + 7-day cache, 304 on revisit |
| Lora fingerprint warmup (151) | none, recomputed on first open | background warmup, persistent sqlite cache (0.5 s after restart) |
| civitai request timeout | `timeout=5000` (seconds — ≈83 min) | 10 s fast-fail |

Key changes: dropped the `import gradio` from the import chain (~3 s for one type hint); dependency install moved to a background thread with a one-shot `.installed` flag (delete the file to force reinstall); `get_group_tags` now uses PyYAML (libyaml C loader) with a 1 s TTL snapshot cache and atomic writes off the event loop; new `script/lora_index.py` replaces full-file sha256 with a 3 MB sample fingerprint backed by an in-memory + SQLite persistent cache (exact sha256 kept for civitai lookups); `get_extra_networks` rewritten as true async concurrency; new `web_perf.py` response layer adds gzip / ETag / Cache-Control globally.

Caveats: tag YAML files are rewritten with PyYAML dump — hand-written comments in `group_tags/*.yaml` are lost after an in-plugin edit (data itself is untouched); the displayed `sha256` field is the sample fingerprint when only local metadata exists.

### New Category: Prompt Studio
Added **Prompt Studio** — a new top-level category with 153 ready-to-use prompt presets sourced from [SD-Anima-Prompt-Studio](https://hajimides.github.io/SD-Anima-Prompt-Studio/):

| Sub-category | Presets |
|:---|---:|
| Quality | 15 |
| Style | 10 |
| Subject | 8 |
| Character | 6 |
| Clothing | 21 |
| Action (Tag) | 10 |
| Action (Natural Language) | 10 |
| Perspective | 10 |
| Composition | 10 |
| Background | 8 |
| NSFW Clothing | 15 |
| NSFW Action (Tag) | 15 |
| NSFW Action (Natural Language) | 15 |

---

## Installation

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/xunying7860/WeiLin-ComfyUI-prompt-all-in-one.git
```

Restart ComfyUI.

---

# Original README Content Below

# Please note that this node no longer accepts any feedback or updates!
### This node is no longer updated and will be replaced by a new node. New node: [WeiLin-Comfyui-Tools](https://github.com/weilin9999/WeiLin-Comfyui-Tools) The new node will continue to update and the installation method of the new node is more convenient and better than that of the old node. The new node is not compatible with the old node, but the Tag data of the old node can be migrated to the new node. Please refer to the new node for more information!

### This plugin is no longer updated! Please use the brand new plugin!
New plugin link: [WeiLin-Comfyui-Tools](https://github.com/weilin9999/WeiLin-Comfyui-Tools)

# Author Statement

Due to limited personal time, the frequency of updating plug-ins will not be very high, occasionally free may update once, each update as far as possible to meet the proposed needs, generally no big BUG basically update frequency is not high, 2~5 a month, thank you for your use and support of this plug-in. You can submit an Issue or you can submit your Request to help update this plugin.

# Version update introduction

> Last updated: 2024-11-26

> 3.6.9.1 Version Introduction (Due to my work, I have time to update the plug-in, forgive me! Thank you very much for your support of this plugin!)
>
> 1. Fixed an issue in the merge code: [#15](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/pull/15) to the modified Lora loading apis in a timeout situation in (thanks for the code contributor provides the help, Thanks to contributors for supporting this plugin, thanks to everyone who uses this plugin)
> 2. Added a new function to load all Lora covers at the bottom of the input box, and the background can view the loading progress. This code is provided by [#15](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/pull/15) contributor

<details>

<summary>
Click here for more updates from the past
</summary>

> 3.6.9 Version Introduction
>
> 1. Fixed known BUG: Offline translation model translation problem in API Settings, fixed

> 3.6.8 Version Introduction
>
> 1. New - Global shortcut key (Set the default to CTRL+ALT+W in ComfyUI Settings to call the global editor)
> 2. New - Floating ball hiding Settings
> 3. Modification - Settings interface optimization ADAPTS to the new UI of the new version of ComfyUI

> 3.6.5 Version Introduction
>
> 1. Fixed Issue: lora's message note is too long, the ui will be stretched and cannot see the content on the right √
> 2. Fixed Issue: tagcomplete in translation Settings could not be used, red letter popped up in the upper right corner, csv file is fine, √ can be used in webui
> 3. Fixed Issue: AttributeError: module 'ctypes' has no attribute 'windll' (Linux language judgment) √
> 4. Fixed the feature: Update will no longer overwrite added Tag information √
> 5. Added the function of shortcut calling the global window
> 6. Added function: Global Paste board preview

> 3.6.1 Version Introduction
>
> 1. Fixed known bugs
> 2. New - In Global Mode, you can enable the Paste board mode. In this mode, you can click any input box in the node to pop up the paste board in global mode
> 3. Fix the -String return string issue

> Version 3.5.0 Introduction
>
> 0. Because the warehouse uploaded some very large files before, 2024-8-16 warehouse was emptied, so the previous version of the warehouse was deleted in order to reduce the size of the warehouse
> 1. Fixed known bugs
> 2. Modified - Restores the functions of the previous version and supports more node collocation
> 3. New - Added the use of local LLM model to help you continue writing prompts

> Version 3.0.0 Introduction
>
> 1. Fixed known bugs
> 2. New -Tag Add, delete, and modify functions
> 3. New - Open the window mode. You can drag the right corner of the window at will to adjust the window size for use in ComfyUI
> 4. Add -Lora viewer. There is a prompt button in the upper right corner of the Lora card to view Lora information and synchronize C station and set the functions of Lora cover
> 5. The new -Lora prompt words are specially adapted to ComfyUI model strength and CLIP strength regulator

> 2.4.0 Version</br>1. Fixed the BUG of prompt word completion </br>2. The NSFW prompt glossary is added only in Chinese </br>3. Added automatic loading of Lora prompt words. You only need to add Lora in PromptUI, which is the same as that in WebUI </br>4. In the setting of ComfyUI, you can change the "Off" button of PromptUI to the right

> 2.3.0 Version</br>1. Added prompt word completion

> 2.2.0 Version </br>1. Fixed known bug</br>2. Updated with new features: Global Prompt UI, Enlarge Window function

</details>

# Lora tips Word writing tips

<lora:xxxx:0.3:0.4> This formulation explains that 0.3 is the model strength and 0.4 is the CLIP strength
If you are <lora:xxxx:0.4> then this interpretation of the model strength and CLIP strength are both 0.4

# Summary

This project allows you to write Prompt words in ComfyUI like WebUI, modified from the prompt-all-in-one project, but has made most of the changes to adapt to ComfyUI, adding many different functions, as well as the plugin for prompt word completion. The prompt word completion plugin is modified from the ComfyUI-Custom-Scripts project. Thank you for your support of this plugin.

If you are interested in this project, please award a Star!

# The installation tutorial can be done directly from git this project

> https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one.git

# Install the plugin in detail, install the version manually

Download the latest release of this project directly, then unzip it, put it in ComfyUI and start ComfyUI directly to use this plugin.
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/1.png)

# How to use the node

Use it as follows
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/2.png)
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/3.png)
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/4.png)

# Plugin Settings preview

![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/5.png)

# WeiLin-ComfyUI-Prompt-all-in-one Reference project

WeiLin-ComfyUI-Prompt-all-in-one The ComfyUI version of prompt-all-in-one, a ComfyUI version modified based on the SD-wewe-prompt-all-in-one-app https://github.com/Physton/sd-webui-prompt-all-in-one-app project, Just add the ComfyUI node of the project to ComfyUI to use the visual tag editor. Cue word completion using the https://github.com/pythongosssss/ComfyUI-Custom-Scripts project changes only the function of the completion and make the changes, Projects using local LLM big model borrowed from https://github.com/thisjam/comfyui-sixgod_prompt warehouse code

# A brief description of this item

At the beginning, the project was just convenient for editing the tag, so I wrote my own plugin, and if you have any questions, you can submit an issue, which may not necessarily be dealt with.
