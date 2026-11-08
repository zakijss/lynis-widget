# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-11-08

### Changed

- Each grade has an icon (a tick from 80, a triangle from 65, a cross below)
  and is read out in words, so the score no longer depends on colour.
- The card's status colours are named tokens (`--lynis-ok`, `--lynis-warn`,
  `--lynis-bad`), one set per theme scheme, each 4.5:1 or better on a widget
  background; dashboard CSS can override them. The 65 to 79 band is amber.
- A drop in the index uses a real minus sign, and the lists open with the
  dashboard's own disclosure style.
