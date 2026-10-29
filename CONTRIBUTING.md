# Contributing to lynis-widget

Bug reports, ideas and pull requests are welcome. Use the issue forms for
the first two; for security problems, see [SECURITY.md](SECURITY.md).

lynis-widget is one file on the Python standard library; please keep it
that way. Strip host names and addresses from any Lynis output you paste into
an issue.

## Before a pull request

Run the self-test, which CI also runs:

```
python3 lynis_widget.py --self-test
```

Keep a pull request to one change, and say in it what changed and why.
Update the README where the change matters to someone running lynis-widget, and
add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).

By contributing you agree that your work is released under the
[MIT licence](LICENSE).
