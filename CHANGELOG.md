# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Each grade has an icon (a tick from 80, a triangle from 65, a cross below)
  and is read out in words, so the score no longer depends on colour.
- The card's status colours are named tokens (`--lynis-ok`, `--lynis-warn`,
  `--lynis-bad`), one set per theme scheme, each 4.5:1 or better on a widget
  background; dashboard CSS can override them. The 65 to 79 band is amber.
- A drop in the index uses a real minus sign, and the lists open with the
  dashboard's own disclosure style.

## [1.1.0] - 2026-11-01

The first public release.

### Added

- `summarize` turns a Lynis report into a small JSON summary per host and
  date; `serve` answers Dynacat and Glance with one card per host: the
  hardening index, how it moved, and the warnings and suggestions with their
  fixes.
- Several hosts in one widget, an optional token, and a link from the title.
- systemd units for the weekly audit and the server, and a rootless Podman
  Quadlet for the server.

[Unreleased]: https://github.com/zakijss/lynis-widget/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/zakijss/lynis-widget/releases/tag/v1.1.0
