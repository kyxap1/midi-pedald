# -*- mode: python ; coding: utf-8 -*-
# onedir, arm64. --onefile would unpack to a temp dir on every KeepAlive launch.
#
# mido picks its backend by string at runtime, so PyInstaller's import graph
# cannot see mido.backends.rtmidi - it must be named here or the daemon fails
# silently at port-open time. https://github.com/orgs/mido/discussions/426

a = Analysis(
    ["main.py"],
    pathex=[".."],
    binaries=[],
    datas=[("../config.example.yaml", ".")],
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
