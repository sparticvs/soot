# soot
Upstream Tracker updater for RPM SPEC files.

This is intended to be used where the RPM SPEC file is in a different repo from
the upstream (essentially if it was in the same repo, the workflow is
different).

## Requirements
  - Use of Python 3.8 or later
  - rpmdev-bumpspec installed (provided by rpmdevtools)

```
$ python -m venv .venv
$ source .venv/bin/activate
$ pip -r requirements.txt
```

## Usage

Update the configuration file to use your details. Recommend installing this to
a crontab or similar.

```
$ python main.py
```
