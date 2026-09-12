---
version: alpha
name: "이리온"
description: "혼잡도를 확인하고 다음 여행을 고르는 한국어 여행 앱"
colors:
  primary: "#2E4636"
  primary-soft: "#E6EEE2"
  background: "#F5F7F4"
  surface: "#FFFFFF"
  text: "#17291F"
  text-muted: "#65736A"
  border: "#DEE5DE"
  estimate-very-low: "#17624B"
  estimate-low: "#26727A"
  estimate-normal: "#356798"
  estimate-high: "#9A5700"
  estimate-very-high: "#AF3038"
typography:
  sans:
    fontFamily: "Pretendard, Noto Sans KR, sans-serif"
    fontSize: "14px"
    lineHeight: "1.5"
rounded:
  DEFAULT: "16px"
  control: "14px"
  featured: "20px"
spacing:
  page-gutter: "20px"
  card-gap: "12px"
  page-max: "560px"
components:
  button: {}
  card: {}
  search: {}
  navigation: {}
---
# 이리온 Design System

## Overview
Korean travelers compare places, check honest congestion observations, find companions and keep their own travel activity. This is a mobile-first product, not a promotional landing page. Original user direction is preserved: green travel identity, compact controls, six bottom tabs, recognizable buildings on the map, prominent points/rewards, separate public reviews and personal reviews.

The visual reference is a practical travel notebook: quiet place cards on a pale green-gray page. The distinctive emphasis is a forest-green points card; surrounding controls stay subdued. No stock hero photography, fake activity counts, rainbow dashboard metrics or ornamental gradients.

Runtime canonical ownership (Model B): `tourist_congestion_frontend/lib/src/theme/app_theme.dart` owns AppColors and AppTheme. This document mirrors those accepted values. AppTheme maps to Material controls; `widgets/app_chrome.dart`, `place_card.dart` and `screens/main_shell.dart` consume it. No CSS/Tailwind token duplication for Flutter CanvasKit. Scope is six primary tabs and shared list/search/navigation primitives; detail/form behavior remains intact.

## Colors
Primary expresses action and selection; primary-soft highlights the current destination. White cards contrast with background without heavy shadows. Text-muted remains readable on white/background. Congestion colors are semantic and always accompanied by words; sample/stale/replaced labels must remain visible. Points retains its original light-gold coin accent. Light theme only; do not advertise a dark-mode switch.

## Typography
Preserve the installed Korean-capable system fallback stack, without new remote font requests. Display role: 24px/700 for page introductions; title role: 18px/700; list title:15–16px/700; body:14px with 1.45–1.65 line height; secondary:12–13px. Numbers use existing intl formatting. No serif headings or English uppercase eyebrows in Korean product screens.

## Layout
Primary column max560 logical pixels, 20px side gutters. Card gaps12, section gaps20–24. Bottom navigation72px plus device safe area, six equal destinations in order Home/Recommendations/Companions/Reviews/Saved/My. Keep Korean labels visible. Pages scroll within their own panels. Search and filters retain state on tab changes. Home map/list control stays top-left. Narrow screens wrap card metadata and scroll filter rows horizontally.

## Elevation & Depth
Use borders and tonal contrast for stationary cards. Avoid ambient shadows; Material popup/dialog elevation signals an overlay. Reserve image boxes during loading and failure. The original prominent points card is the only large dark surface on My.

## Shapes
Cards16px, featured surfaces20px, text fields14px. Filter/navigation pills20px or more. Maps retain their established clipped frame. Do not turn every section into another nested card.

## Components
Buttons use Material focus, hover, pressed and disabled states. Primary fill is forest green; outline borders use the common border token. Default primary actions48px, secondary44px; compact filters36px retain text labels. Busy controls retain their labels/width and block duplicates.

Shared AppSearchField owns the clear control and focus return. Home submits explicitly to the API; companion search filters the fetched list locally. Do not add network requests per keystroke or modify composing Korean text. RegionPicker and Material date/select popups retain current logic.

Lists use actual images; missing photos use a muted landscape icon explicitly labelled as missing, never invented photography. Status labels explain missing, sample and stale information. Empty states describe the next valid action. Errors retain retry controls. Loading is the existing progress indicator, not fake content.

Material icon family,22px navigation/20–24px actions. Selected navigation combines fill, text weight and semantics. Motion is feedback only; reduced-motion setting bypasses map zoom animation. Snackbar/AlertDialog/showModalBottomSheet remain canonical; no browser alert/confirm/prompt.

## Do's and Don'ts
- Do preserve API data, routes, session boundaries, guest favorites and source attribution.
- Do keep points visually prominent without inventing redeemable benefits.
- Do use original content and Korean action labels.
- Don't replace six tabs, move accepted map controls or hide stale data in pursuit of simplicity.
- Don't import API keys into frontend code, URLs, build artifacts or Git.

Companion create and detail use a continuous white surface with clear labels and thin section dividers, informed by the official Danggn posting-screen reference. Create prioritizes title and full description before place/date/capacity; detail prioritizes the organizer, title and full body before compact trip facts. Existing registration and join/cancel/delete actions remain in safe-area footers; content scrolls independently. No unsupported photo upload or AI-writing controls are introduced.

The public Reviews tab is a cross-place travel feed, not a rating summary. Prominent place titles link to place-specific reviews; photos span the feed card. Aggregate ratings remain exclusive to place-specific review routes; personal reviews remain management-only.

Place detail preserves the image/name/directions/congestion hero. Below it, a 52px pinned section bar links instantly to introduction, visitor information, and embedded place reviews. The parent owns scrolling; active tabs follow scroll position and section headings remain below the pinned bar.
The community review tab shares AppSearchField, compact filters, card spacing, and the companion-style floating compose action. Search filters loaded reviews by place/content/author; place-specific and personal review variants keep their distinct layouts.


### Crowd estimate extension
The five estimate colors map to AppColors.estimateVeryLow/Low/Normal/High/VeryHigh. Text labels carry meaning independently of color. CrowdBadge and CrowdEvidence share wording across all place surfaces; prior and low evidence states remain explicit. Forecast cards wrap on narrow screens. Existing primary forest palette and navigation remain canonical.
