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
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# The platform runs the official release, which arc-linux-release.yml builds on
# ubuntu-latest (24.04, glibc 2.39): that binary needs GLIBC_2.39 at most and is
# known to load there. A build needing a newer glibc does not: run e70711133d37
# hung for good on a local build needing GLIBC_2.43 (host: Ubuntu glibc 2.43) --
# the loader refused it and the stdio driver waited on a handshake that never
# came. Raise the ceiling with ARC_KERNEL_MAX_GLIBC only once the platform image
# is known to be newer; the safe way to ship a modified kernel is the CI release.
PLATFORM_MAX_GLIBC = (2, 39)

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


def max_glibc(path: Path) -> tuple[int, int] | None:
    """Highest GLIBC_x.y version string in the binary (its .dynstr carries one
    per versioned symbol it imports, and a stripped binary keeps them). None for
    a binary with no such strings -- static or musl -- which loads anywhere.
    A plain scan of the bytes is over-inclusive at worst, which only ever
    refuses; it needs no objdump."""
    found = {(int(a), int(b)) for a, b in re.findall(rb"GLIBC_(\d+)\.(\d+)", Path(path).read_bytes())}
    return max(found) if found else None


def glibc_ceiling() -> tuple[int, int]:
    raw = os.environ.get("ARC_KERNEL_MAX_GLIBC", "").strip()
    if raw:
        major, minor = raw.split(".", 1)
        return (int(major), int(minor))
    return PLATFORM_MAX_GLIBC


def usable_kernel(path: Path) -> str | None:
    """None when the binary can be shipped; otherwise why not."""
    if not linux_x86_64_elf(path):
        return "not a Linux x86_64 ELF"
    need = max_glibc(path)
    ceiling = glibc_ceiling()
    if need and need > ceiling:
        return (f"needs GLIBC_{need[0]}.{need[1]}, the platform has at most {ceiling[0]}.{ceiling[1]}"
                " (build on an older glibc, e.g. the CI release on ubuntu-latest, or set ARC_KERNEL_MAX_GLIBC)")
    return None


def find_kernel(repo_root: Path, override: str | None = None, reasons: list[str] | None = None) -> Path | None:
    """The kernel to ship, or None to leave the bundle on the download path.

    `arc/bin/octos` first (an explicit "ship this one"), then a cross-compiled
    Linux target, then the host build. Every candidate must be a Linux x86_64
    ELF that needs no newer glibc than the platform has; `reasons` collects why
    each existing candidate was passed over."""
    candidates = [override] if override else []
    candidates += [repo_root / "arc" / "bin" / "octos",
                   repo_root / "target" / "x86_64-unknown-linux-gnu" / "release" / "octos",
                   repo_root / "target" / "release" / "octos"]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        why = usable_kernel(Path(candidate))
        if why is None:
            return Path(candidate)
        if reasons is not None:
            reasons.append(f"{candidate}: {why}")
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
    reasons: list[str] = []
    binary = find_kernel(repo_root, argv[2] if len(argv) > 2 else os.environ.get("ARC_KERNEL_BIN"), reasons)
    if binary is None:
        for why in reasons:
            print(f"跳过 {why}")
        print("未自带内核（没找到平台能加载的 Linux x86_64 octos）；平台将按 OCTOS_RELEASE_URL 下载")
        return 0
    size = add_kernel(bundle, binary)
    print(f"包含自带内核：{ENTRY} <- {binary}（strip 后 {size / 1024 / 1024:.0f}M）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
