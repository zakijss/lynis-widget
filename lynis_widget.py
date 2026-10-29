#!/usr/bin/env python3
"""Lynis results as a Dynacat or Glance extension widget.

summarize (as root, after Lynis) copies what the widget shows from Lynis's
report.dat into DIR/<host>-<date>.json, readable by anyone. serve answers the
dashboard with one card per host, from the newest summaries anywhere under its
DIR. README.md has the details.
"""
import argparse
import datetime
import glob
import html
import hmac
import json
import os
import re
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"
REPORT = "/var/log/lynis-report.dat"
PROFILE = "/etc/lynis/custom.prf"
OUT = "/var/lib/lynis-widget"


# ---- summarize ----------------------------------------------------------------

def find_lynis():
    """Lynis's install folder (for test names), or None."""
    for d in ["/usr/share/lynis", "/usr/local/lib/lynis", "/usr/local/lynis", "/opt/lynis",
              *sorted(glob.glob("/usr/local/lib/lynis-*"), reverse=True)]:
        if os.path.isdir(os.path.join(d, "include")):
            return d
    return None


def test_names(lynis):
    """{test ID: (category, description)} from Lynis's test files, if found."""
    if not lynis:
        return {}
    names, out = {}, {}
    try:
        with open(os.path.join(lynis, "db/languages/en"), encoding="utf-8", errors="replace") as f:
            names = dict(re.findall(r'^(SECTION_\w+)="(.*)"', f.read(), re.M))
    except OSError:
        pass
    for path in sorted(glob.glob(os.path.join(lynis, "include/tests_*"))):
        section = "Other"
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r'\s*InsertSection "(.*)"', line)
                if m:
                    v = re.fullmatch(r"\$\{(\w+)\}", m[1])
                    section = names.get(v[1], v[1]) if v else m[1]
                    continue
                m = re.search(r'Register --test-no (\S+).*?--description "([^"]*)"', line)
                if m:
                    out[m[1]] = (section, m[2])
    return out


def parse(text):
    """report.dat's single values, and its warnings and suggestions as
    {id, text, details, solution} ("-", Lynis's empty field, becomes "")."""
    one, found = {}, {"warning": [], "suggestion": []}
    clean = lambda s: "" if s.strip() == "-" else s.strip()
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        kind = key[:-2]
        if key.endswith("[]") and kind in found:
            f = value.removesuffix("|").split("|")
            f += ["-"] * (4 - len(f))
            found[kind].append({"id": f[0].strip(), "text": clean("|".join(f[1:-2])),
                                "details": clean(f[-2]), "solution": clean(f[-1])})
        elif not key.endswith("[]"):
            one[key] = value
    return one, found


def accepted(path):
    """[{id, reason}]: each skip-test line of a Lynis profile, with the comment
    block above it (up to a blank line) as its reason."""
    out, why = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            why.append(line.lstrip("#").strip())
        elif line.startswith("skip-test="):
            out.append({"id": line.split("=", 1)[1].strip(), "reason": " ".join(why)})
        elif not line:
            why = []
    return out


def summary(text, known, host, acc):
    one, found = parse(text)
    num = lambda k: int(one[k]) if one.get(k, "").isdigit() else None
    started = one.get("report_datetime_start", "")
    date = started[:10] if re.match(r"\d{4}-\d{2}-\d{2}", started) else datetime.date.today().isoformat()

    def item(i):
        category, description = known.get(i["id"], ("Other", ""))
        return {**i, "category": category, "description": description}

    return {"host": host, "date": date, "started": started, "lynis": one.get("lynis_version", ""),
            "os": one.get("os_fullname", ""), "index": num("hardening_index"), "tests": num("lynis_tests_done"),
            "warnings": [item(i) for i in found["warning"]],
            "suggestions": [item(i) for i in found["suggestion"]], "accepted": acc}


def write(s, out, keep):
    """The summary as <host>-<date>.json, readable by anyone; the oldest beyond keep go."""
    old = os.umask(0o022)
    os.makedirs(out, exist_ok=True)
    os.umask(old)
    path = os.path.join(out, f"{s['host']}-{s['date']}.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    os.chmod(path + ".tmp", 0o644)
    os.replace(path + ".tmp", path)
    mine = re.compile(re.escape(s["host"]) + r"-\d{4}-\d{2}-\d{2}\.json")   # so rotating "web" spares "web-2-..."
    runs = sorted(p for p in glob.glob(os.path.join(out, "*.json")) if mine.fullmatch(os.path.basename(p)))
    for stale in runs[:-keep]:
        os.remove(stale)
    return path


# ---- serve ----------------------------------------------------------------------

def load(folder):
    """{host: (newest summary, previous summary or None)} from every *.json
    under DIR, subfolders included; the host comes from each file's contents."""
    by_host = {}
    for path in glob.glob(os.path.join(folder, "**", "*.json"), recursive=True):
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(s, dict) and s.get("host") and s.get("date"):
            by_host.setdefault(s["host"], []).append(s)
    out = {}
    for host, runs in by_host.items():
        runs.sort(key=lambda s: (s["date"], s.get("started", "")), reverse=True)
        out[host] = (runs[0], runs[1] if len(runs) > 1 else None)
    return out


def grade(index):
    """Dynacat colour class for a hardening index."""
    if index is None:
        return "color-subdue"
    return "color-positive" if index >= 80 else "color-highlight" if index >= 65 else "color-negative"


def when(started):
    """Unix time of report_datetime_start (local time), or None."""
    try:
        return int(time.mktime(time.strptime(started, "%Y-%m-%d %H:%M:%S")))
    except (ValueError, TypeError):
        return None


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def findings(label, items, cls):
    if not items:
        return ""
    e = html.escape
    rows = "".join(
        f'<li><span class="{cls}">{e(i.get("id", ""))}</span> {e(i.get("text", ""))}'
        + (f'<div class="color-subdue size-h6">{e(i["solution"])}</div>' if i.get("solution") else "")
        + "</li>" for i in items)
    return (f'<details class="margin-top-5"><summary class="size-h5">{label}</summary>'
            f'<ul class="list list-gap-8 margin-top-5 size-h6">{rows}</ul></details>')


def render(hosts):
    e = html.escape
    if not hosts:
        return ('<p class="color-subdue">No Lynis summaries yet. Run <code>lynis audit system</code>, '
                'then <code>lynis_widget.py summarize</code>.</p>')
    cards = []
    for host in sorted(hosts):
        s, prev = hosts[host]
        idx, ts = s.get("index"), when(s.get("started", ""))
        delta = ""
        if prev and idx is not None and prev.get("index") is not None and idx != prev["index"]:
            d = idx - prev["index"]
            delta = f' <span class="{"color-positive" if d > 0 else "color-negative"}">{"+" if d > 0 else ""}{d}</span>'
        age = f'<span data-dynamic-relative-time="{ts}"></span> ago' if ts else e(s.get("date", ""))
        meta = " · ".join(x for x in (e(s.get("os", "")), f'{s.get("tests") or "?"} tests', age) if x)
        w, sg, acc = s.get("warnings") or [], s.get("suggestions") or [], s.get("accepted") or []
        counts = (f'<span class="{"color-negative" if w else "color-subdue"}">{plural(len(w), "warning")}</span>'
                  f' · {plural(len(sg), "suggestion")}' + (f' · {len(acc)} accepted' if acc else ""))
        cards.append(
            '<li><div class="flex justify-between items-center">'
            f'<span class="size-h3 color-highlight">{e(host)}</span>'
            f'<span class="size-h1 {grade(idx)}" title="Lynis hardening index, out of 100">{idx if idx is not None else "?"}{delta}</span>'
            f'</div><div class="size-h6 color-subdue">{meta}</div><div class="size-h5 margin-top-5">{counts}</div>'
            + findings(plural(len(w), "warning"), w, "color-negative")
            + findings(plural(len(sg), "suggestion"), sg, "color-primary")
            + findings(f"{len(acc)} accepted on purpose",
                       [{"id": a.get("id", ""), "text": a.get("reason", "")} for a in acc], "color-subdue") + "</li>")
    return f'<ul class="list list-gap-20 list-with-separator">{"".join(cards)}</ul>'


class Handler(BaseHTTPRequestHandler):
    server_version = f"lynis-widget/{VERSION}"
    folder, title, link, token = OUT, "Lynis", "", ""    # set from the flags in main()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            return self.reply(200, "ok", {"Content-Type": "text/plain"})
        if path != "/":
            return self.reply(404, "not found", {"Content-Type": "text/plain"})
        if self.token:
            got = self.headers.get("Authorization", "")
            if not hmac.compare_digest(got.encode(), f"Bearer {self.token}".encode()):
                return self.reply(401, "token required", {"Content-Type": "text/plain"})
        headers = {"Content-Type": "text/html; charset=utf-8", "Widget-Title": self.title,
                   "Widget-Content-Type": "html", "Cache-Control": "no-store"}
        if self.link:
            headers["Widget-Title-URL"] = self.link
        self.reply(200, render(load(self.folder)), headers)

    def reply(self, code, body, headers):
        data = body.encode()
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):      # errors only; the widget is polled
        if len(args) > 1 and str(args[1])[:1] in "45":
            sys.stderr.write(f"{self.address_string()} {format % args}\n")


# ---- self-test --------------------------------------------------------------------

def self_test():
    import tempfile
    report = ("report_datetime_start=2026-10-17 16:07:58\nlynis_version=3.1.7\nos_fullname=Fedora Linux 44\n"
              "lynis_tests_done=263\nhardening_index=82\n"
              "warning[]=AUTH-9216|grpck binary found errors in one or more group files|-|-|\n"
              "suggestion[]=FILE-6362|Set the sticky bit on /tmp|/tmp|text:Set sticky bit|\n"
              "suggestion[]=STRG-1930|Check a|b in the text|-|-|\n"
              "suggestion[]=XYZ-1|short\n")
    s = summary(report, {"AUTH-9216": ("Users", "Check group files")}, "box", [{"id": "X-1", "reason": "r"}])
    assert s["index"] == 82 and s["tests"] == 263 and s["date"] == "2026-10-17", s
    assert s["warnings"][0]["category"] == "Users" and s["warnings"][0]["details"] == ""
    assert s["suggestions"][1]["text"] == "Check a|b in the text"
    assert s["suggestions"][2] == {"id": "XYZ-1", "text": "short", "details": "", "solution": "",
                                   "category": "Other", "description": ""}
    with tempfile.TemporaryDirectory() as d:
        prof = os.path.join(d, "p.prf")
        open(prof, "w").write("# why one\n# more\nskip-test=A-1\n\nskip-test=B-2\n")
        assert accepted(prof) == [{"id": "A-1", "reason": "why one more"}, {"id": "B-2", "reason": ""}]
        old = dict(s, date="2026-10-10", started="2026-10-10 10:00:00", index=78)
        write(old, d, 5)
        p = write(s, d, 5)
        assert oct(os.stat(p).st_mode & 0o777) == "0o644"
        write(dict(s, host="other", index=55, warnings=[], suggestions=[]), d, 5)
        write(dict(s, host="box-2"), os.path.join(d, "sub"), 5)   # a collector's per-host subfolder
        hosts = load(d)
        assert set(hosts) == {"box", "box-2", "other"} and hosts["box"][1]["index"] == 78
        write(dict(s, host="box-2"), d, 5)
        out = render(hosts)
        assert "color-positive" in out and "+4" in out and "1 warning<" in out and "3 suggestions" in out, out
        assert "color-negative" in out                      # other's 55
        assert "1 accepted on purpose" in out and ">X-1<" in out
        for i in range(7):
            write(dict(s, date=f"2026-09-0{i + 1}"), d, 3)
        assert len(glob.glob(os.path.join(d, "box-2???-*.json"))) == 3
        assert os.path.exists(os.path.join(d, "box-2-2026-10-17.json"))   # box's rotation left box-2 alone
    evil = dict(s, host="<script>x</script>", warnings=[{"id": "<b>", "text": "<img src=x onerror=alert(1)>"}])
    out = render({"h": (evil, None)})
    assert "<script>" not in out and "<img" not in out and "&lt;img" in out
    assert "No Lynis summaries yet" in render({})
    assert grade(None) == "color-subdue" and grade(80) == "color-positive" and grade(64) == "color-negative"
    one = [{"id": "X-1", "text": "t"}]
    assert ">1 warning<" in findings(plural(1, "warning"), one, "c") and plural(2, "warning") == "2 warnings"
    print("self-test ok")


def main():
    ap = argparse.ArgumentParser(description="Lynis results as a Dynacat or Glance extension widget.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd")
    sm = sub.add_parser("summarize", help="write a summary of Lynis's report (run as root)")
    sm.add_argument("--report", default=REPORT, help=f"Lynis's report.dat (default {REPORT})")
    sm.add_argument("--profile", default=PROFILE, help=f"a Lynis profile with skip-test lines (default {PROFILE})")
    sm.add_argument("--lynis-dir", help="Lynis's install folder, for test names (found by default)")
    sm.add_argument("--host", default=socket.gethostname().split(".")[0], help="the name to show (default: this host)")
    sm.add_argument("--out", default=OUT, help=f"where summaries go (default {OUT})")
    sm.add_argument("--keep", type=int, default=12, help="summaries kept per host (default 12)")
    sv = sub.add_parser("serve", help="serve the widget")
    sv.add_argument("--dir", default=os.environ.get("LYNIS_WIDGET_DIR", OUT), help=f"summaries to show (default {OUT})")
    sv.add_argument("--bind", default=os.environ.get("LYNIS_WIDGET_BIND", "127.0.0.1"))
    sv.add_argument("--port", type=int, default=int(os.environ.get("LYNIS_WIDGET_PORT", "8121")))
    sv.add_argument("--title", default=os.environ.get("LYNIS_WIDGET_TITLE", "Lynis"))
    sv.add_argument("--link", default=os.environ.get("LYNIS_WIDGET_LINK", ""), help="URL the widget's title opens")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.cmd == "summarize":
        try:
            with open(a.report, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.exit(f"can't read {a.report}: {e} (run Lynis first, as root)")
        s = summary(text, test_names(a.lynis_dir or find_lynis()), a.host, accepted(a.profile))
        print(f"index {s['index']}, {plural(len(s['warnings']), 'warning')}, {plural(len(s['suggestions']), 'suggestion')}: "
              f"{write(s, a.out, a.keep)}")
    elif a.cmd == "serve":
        if not os.path.isdir(a.dir):
            sys.exit(f"{a.dir} is not a folder; point --dir (or LYNIS_WIDGET_DIR) at your summaries")
        Handler.folder, Handler.title, Handler.link = a.dir, a.title, a.link
        Handler.token = os.environ.get("LYNIS_WIDGET_TOKEN", "")
        print(f"serving {a.dir} on http://{a.bind}:{a.port}/", flush=True)
        ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
