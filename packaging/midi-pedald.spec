# -*- mode: python ; coding: utf-8 -*-
# onedir, arm64. --onefile would unpack to a temp dir on every KeepAlive launch.
#
# mido picks its backend by string at runtime, so PyInstaller's import graph
# cannot see mido.backends.rtmidi - it must be named here or the daemon fails
# silently at port-open time. https://github.com/orgs/mido/discussions/426

import os

_repo_root = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[_repo_root],
    binaries=[],
    datas=[(os.path.join(_repo_root, "config.example.yaml"), ".")],
    hiddenimports=["mido.backends.rtmidi", "rtmidi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="midi-pedald",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="midi-pedald",
)
