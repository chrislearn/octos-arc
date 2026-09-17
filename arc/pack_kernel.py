#!/usr/bin/env python3
"""Put the Linux kernel binary into the submission zip as `bin/octos`.

`main.py`'s find_octos() prefers a bundled `bin/octos` over downloading
OCTOS_RELEASE_URL, so this is what makes a locally built kernel the one the
platform actually runs. That preference is also why the binary is checked
before it is packed: a macOS or aarch64 build would be handed to the platform
and die on spawn, with no fall-through to the download that would have worked.

usage: pack_kernel.py <bundle.zip> [binary]   (env: ARC_KERNEL_BIN, ARC_PACK_KERNEL=0)
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
ELF_CLASS_64 = 2
EM_X86_64 = 0x3E
ENTRY = "bin/octos"


def linux_x86_64_elf(path: Path) -> bool:
    """Read the ELF header rather than shelling out to `file`, which is not
    installed everywhere and prints a different string on every platform."""
    try:
        head = Path(path).read_bytes()[:20]
    except OSError:
        return False
    if len(head) < 20 or head[:4] != ELF_MAGIC or head[4] != ELF_CLASS_64:
        return False
    return struct.unpack_from("<H", head, 18)[0] == EM_X86_64


def find_kernel(repo_root: Path, override: str | None = None) -> Path | None:
    """The kernel to ship, or None to leave the bundle on the download path.

    `arc/bin/octos` first (an explicit "ship this one"), then a cross-compiled
    Linux target, then the host build -- which is only usable when the host is
    Linux x86_64, hence the same ELF check on every candidate."""
    candidates = [override] if override else []
    candidates += [repo_root / "arc" / "bin" / "octos",
                   repo_root / "target" / "x86_64-unknown-linux-gnu" / "release" / "octos",
                   repo_root / "target" / "release" / "octos"]
    for candidate in candidates:
        if candidate and linux_x86_64_elf(Path(candidate)):
            return Path(candidate)
    return None


def add_kernel(bundle: Path, binary: Path) -> int:
    """Append the binary as bin/octos, stripped when the toolchain allows it.

    The entry is marked 0755 for unzippers that keep the mode; the ones that do
    not (Python's zipfile) are handled by find_octos() restoring the bit."""
    with tempfile.TemporaryDirectory() as tmp:
        shipped = Path(tmp) / "octos"
        if shutil.which("strip") and subprocess.run(
                ["strip", "-o", str(shipped), str(binary)], check=False).returncode == 0:
            pass  # stripped copy; the original keeps its symbols for local debugging
        else:
            shutil.copy2(binary, shipped)
        stamp = __import__("time").localtime(binary.stat().st_mtime)
        info = zipfile.ZipInfo(ENTRY, date_time=stamp[:6])
        info.external_attr = 0o755 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(bundle, "a", compression=zipfile.ZIP_DEFLATED) as z:
            with z.open(info, "w") as target, shipped.open("rb") as source:
                shutil.copyfileobj(source, target)
        return shipped.stat().st_size


def main(argv: list[str]) -> int:
    bundle = Path(argv[1])
    if os.environ.get("ARC_PACK_KERNEL") == "0":
        print("跳过自带内核（ARC_PACK_KERNEL=0）；平台将按 OCTOS_RELEASE_URL 下载")
        return 0
    repo_root = Path(__file__).resolve().parent.parent
    binary = find_kernel(repo_root, argv[2] if len(argv) > 2 else os.environ.get("ARC_KERNEL_BIN"))
    if binary is None:
        print("未自带内核（没找到 Linux x86_64 的 octos）；平台将按 OCTOS_RELEASE_URL 下载")
        return 0
    size = add_kernel(bundle, binary)
    print(f"包含自带内核：{ENTRY} <- {binary}（strip 后 {size / 1024 / 1024:.0f}M）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
