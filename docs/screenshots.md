# System QuikView gallery

## Marketplace cover and native demos — 0.4.7, 19 October 2026

The root `preview.png` is a promotional one-sheet in the same visual family as OmaChat and OmaDroid. OpenAI's built-in image generation produced the composition from native 0.4.7 QML captures with invented readings. It is promotional artwork, not a pixel-exact screenshot or a claim that every sensor is available on every machine. [Generation prompt](artwork/marketplace-cover-prompt.txt).

![System QuikView marketplace cover with simulated readings](../preview.png)

These unedited native captures use an isolated collector stub, synthetic readings and the real current panel. No user telemetry or installed plugin was used or changed. The dark fan card shows simulated kernel RPM, including a true stopped-fan zero; the light card shows a simulated publisher duty estimate, not RPM. The overview intentionally collapses sections; its integrated GPU has shared system memory and no dedicated VRAM. Captured on Omarchy 4.0.5, Quickshell 0.3.2 and Qt 6.12.

<img src="screenshots/demo-overview-v0.4.7-dark.png" width="400" alt="Native dark overview with simulated CPU, memory, integrated GPU, storage and network readings">
<img src="screenshots/demo-fans-v0.4.7-dark.png" width="560" alt="Native Fans detail with simulated 0 and 2410 RPM tachometers">
<img src="screenshots/demo-fans-v0.4.7-light.png" width="560" alt="Native light Fans detail showing a simulated 47 percent duty estimate rather than RPM">

## Earlier gallery

Real screenshots from Omarchy Shell, using live readings from an AMD integrated / NVIDIA dedicated laptop. Sections are collapsed and reordered to highlight each view; all of these controls are available in Customize. Longer views scroll.

## Overview

<img src="screenshots/overview-onelegdave.png" width="480" alt="Compact dashboard in the custom OneLegDave theme">

## Make it yours

Move sections individually and choose the reading in your bar. GPU source selection and role overrides are farther down the settings view.

<img src="screenshots/customize.png" width="480" alt="Customization screen with section order and bar metric controls">

## Network

Independent download and upload histories, recent peaks, and per-interface counters. Inactive interfaces can be revealed when needed.

<img src="screenshots/network.png" width="480" alt="Network traffic charts and interface cards">

## Temperatures

Device groups keep sensor names, current readings, and hardware limits together. This capture shows the top of the scrollable temperature section.

<img src="screenshots/temperatures.png" width="480" alt="CPU and graphics temperature cards">

## Top processes

Ranked process cards pair CPU usage with resident memory. The two comparison bars use separate scales.

<img src="screenshots/processes.png" width="480" alt="Top processes ranked by CPU with memory readings">

## Dark and light themes

These are captures after applying each installed Omarchy theme. QuikView reads the active palette automatically.

| Catppuccin | Gruvbox | Catppuccin Latte |
| --- | --- | --- |
| <img src="screenshots/overview-catppuccin.png" width="280" alt="Catppuccin"> | <img src="screenshots/overview-gruvbox.png" width="280" alt="Gruvbox"> | <img src="screenshots/overview-catppuccin-latte.png" width="280" alt="Catppuccin Latte light theme"> |

[Back to installation and features](../README.md)
