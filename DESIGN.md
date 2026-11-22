---
version: alpha
name: Middlewar prototype system
description: Normative visual system extracted from design-prototype/style.css for the Middlewar web application.
colors:
  bg: "#0b0d0c"
  bg2: "#111411"
  card: "#171a17"
  card2: "#1d211d"
  text: "#e8e4d8"
  muted: "#97998f"
  gold: "#bda56d"
  gold2: "#d3bc83"
  gold3: "#74633e"
  green: "#68765c"
  red: "#87453c"
  line: "rgba(210, 190, 140, 0.16)"
  glass: "rgba(13, 16, 14, 0.84)"
typography:
  body:
    fontFamily: "Inter, Manrope, Arial, sans-serif"
    fontSize: 14px
    lineHeight: 1.5
  display:
    fontFamily: "Cinzel, Georgia, serif"
    letterSpacing: 0.035em
rounded:
  base: 10px
---

## Overview

Middlewar is a dark strategic campaign interface. The static screens in `design-prototype/` are the normative source for the shared visual language and matching route composition.

## Colors

Use the dark background and card roles consistently across public and authenticated routes. Gold roles carry emphasis and campaign status; green and red are reserved for opposing game states. Borders and glass surfaces use the shared translucent roles instead of page-local substitutes.

## Typography

Body copy and controls use the body scale. Page, section, card, and metric headings use the display scale. Small navigation and metadata labels use uppercase lettering only where the prototype does.

## Layout

Matching routes follow the corresponding prototype HTML hierarchy at desktop and mobile widths. Additional application-only routes reuse the same container, section rhythm, card grid, navigation, and responsive breakpoints.

## Elevation & Depth

Route backgrounds use the supplied prototype artwork with its fixed dark overlay. Cards combine the prototype gradient surface, shared border, shadow, and backdrop blur; nested controls stay flatter so hierarchy remains visible.

## Shapes

Use the shared radius for primary cards and modals. Inner controls, chips, and tabs keep the tighter shapes defined by the prototype instead of inheriting the card radius.

## Components

The shared top bar, page title, cards, panels, tabs, tables, inputs, buttons, status labels, and modal shell must retain the states and responsive behavior shown in `design-prototype/style.css`. A matching route may bind different live data, but it must not replace the prototype composition with a generic component layout.
