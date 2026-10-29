# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-27

The first public release.

### Added

- `summarize` turns a Lynis report into a small JSON summary per host and
  date; `serve` answers Dynacat and Glance with one card per host: the
  hardening index, how it moved, and the warnings and suggestions with their
  fixes.
- Several hosts in one widget, an optional token, and a link from the title.
- systemd units for the weekly audit and the server, and a rootless Podman
  Quadlet for the server.

[Unreleased]: https://github.com/zakijss/lynis-widget/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/zakijss/lynis-widget/releases/tag/v1.0.0
