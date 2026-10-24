# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('src/accoach/web', 'accoach/web'), ('src/accoach/voice_cues', 'accoach/voice_cues'), ('src/accoach/tracks', 'accoach/tracks'), ('src/accoach/voice_cues_male', 'accoach/voice_cues_male'), ('GUIDA.md', '.'), ('docs/FAQ.md', 'docs')]
binaries = []
hiddenimports = ['pyttsx3.drivers', 'pyttsx3.drivers.sapi5']
hiddenimports += collect_submodules('uvicorn')
tmp_ret = collect_all('comtypes')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['accoach_main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HONE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX spento qui e nel COLLECT: un EXE e delle DLL compressi da un packer
    # sono quello che gli antivirus segnalano per primo, anche quando il file
    # e' pulito. Si evitano i falsi positivi, non c'entra la provenienza.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['hone.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='HONE',
)
