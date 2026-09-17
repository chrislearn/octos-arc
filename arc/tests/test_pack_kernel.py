"""pack.sh decides whether the kernel travels inside the submission zip.

Packing the wrong binary fails worse than packing none: find_octos() prefers a
bundled bin/octos over the OCTOS_RELEASE_URL download, so a macOS build (or a
stale artifact) would be handed to the platform and the spawn would die with no
fall-through. Hence the ELF check, and hence these tests.
"""
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pack_kernel as pk


def elf(machine=0x3E, klass=2, magic=b"\x7fELF"):
    """Minimal ELF header: magic, 64-bit class, little endian, e_machine."""
    head = bytearray(magic + bytes([klass, 1, 1]) + b"\0" * 9)
    head += struct.pack("<HH", 3, machine)  # e_type = DYN (PIE), e_machine
    return bytes(head) + b"\0" * 64


class ElfCheckTests(unittest.TestCase):
    def _write(self, folder, data, name="octos", mode=0o755):
        path = Path(folder) / name
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def test_should_accept_a_linux_x86_64_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(pk.linux_x86_64_elf(self._write(folder, elf())))

    def test_should_reject_a_mach_o_or_arm64_or_32_bit_build(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(pk.linux_x86_64_elf(self._write(folder, b"\xcf\xfa\xed\xfe" + b"\0" * 80)))
            self.assertFalse(pk.linux_x86_64_elf(self._write(folder, elf(machine=0xB7))))  # aarch64
            self.assertFalse(pk.linux_x86_64_elf(self._write(folder, elf(klass=1))))       # 32-bit

    def test_should_reject_a_missing_or_truncated_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(pk.linux_x86_64_elf(Path(folder) / "absent"))
            self.assertFalse(pk.linux_x86_64_elf(self._write(folder, b"\x7fELF")))


class KernelDiscoveryTests(unittest.TestCase):
    def _repo(self, folder, *rels):
        root = Path(folder)
        for rel in rels:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(elf())
            path.chmod(0o755)
        return root

    def test_should_prefer_an_explicit_override_over_the_build_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._repo(folder, "arc/bin/octos", "target/release/octos")
            self.assertEqual(pk.find_kernel(root, override=str(root / "arc/bin/octos")),
                             root / "arc/bin/octos")

    def test_should_prefer_arc_bin_then_the_cross_target_then_the_host_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._repo(folder, "arc/bin/octos",
                              "target/x86_64-unknown-linux-gnu/release/octos", "target/release/octos")
            self.assertEqual(pk.find_kernel(root), root / "arc/bin/octos")
            (root / "arc/bin/octos").unlink()
            self.assertEqual(pk.find_kernel(root), root / "target/x86_64-unknown-linux-gnu/release/octos")
            (root / "target/x86_64-unknown-linux-gnu/release/octos").unlink()
            self.assertEqual(pk.find_kernel(root), root / "target/release/octos")

    def test_should_skip_a_build_that_is_not_linux_x86_64(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target/release").mkdir(parents=True)
            (root / "target/release/octos").write_bytes(b"\xcf\xfa\xed\xfe" + b"\0" * 80)
            self.assertIsNone(pk.find_kernel(root))

    def test_should_find_nothing_when_nothing_was_built(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(pk.find_kernel(Path(folder)))


class AddKernelTests(unittest.TestCase):
    def test_should_store_the_binary_at_bin_octos_whatever_its_source_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / "target" / "release" / "octos"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(elf())
            bundle = root / "b.zip"
            with zipfile.ZipFile(bundle, "w") as z:
                z.writestr("main.py", "x")
            pk.add_kernel(bundle, binary)
            with zipfile.ZipFile(bundle) as z:
                self.assertIn("bin/octos", z.namelist())
                self.assertEqual(z.read("bin/octos")[:4], b"\x7fELF")

    def test_should_mark_the_entry_executable_for_unzippers_that_keep_the_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / "octos"
            binary.write_bytes(elf())
            bundle = root / "b.zip"
            with zipfile.ZipFile(bundle, "w") as z:
                z.writestr("main.py", "x")
            pk.add_kernel(bundle, binary)
            with zipfile.ZipFile(bundle) as z:
                mode = z.getinfo("bin/octos").external_attr >> 16
            self.assertTrue(mode & 0o111, f"mode {mode:o} has no exec bit")


class GlibcCeilingTests(unittest.TestCase):
    """Run e70711133d37 hung on the platform: the bundled kernel was built on a
    host with glibc 2.43 and needed GLIBC_2.43, while the official release
    (built on ubuntu-latest) needs at most GLIBC_2.39 and runs there. The loader
    refused ours, the stdio driver waited on a handshake that never came. A
    candidate needing a newer glibc than the platform's must not be packed."""

    def _write(self, folder, tail, name="octos"):
        path = Path(folder) / name
        path.write_bytes(elf() + tail)
        path.chmod(0o755)
        return path

    def test_should_read_the_highest_glibc_version_a_binary_needs(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(pk.max_glibc(self._write(folder, b"GLIBC_2.38\0GLIBC_2.43\0GLIBC_2.39\0")), (2, 43))
            self.assertIsNone(pk.max_glibc(self._write(folder, b"no versioned symbols", "static")))

    def test_should_refuse_a_build_that_needs_a_newer_glibc_than_the_platform(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target/release").mkdir(parents=True)
            self._write(root / "target/release", b"GLIBC_2.43\0")
            reasons = []
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ARC_KERNEL_MAX_GLIBC", None)
                self.assertIsNone(pk.find_kernel(root, reasons=reasons))
            self.assertTrue(any("GLIBC_2.43" in r and "2.39" in r for r in reasons), reasons)

    def test_should_accept_a_build_within_the_ceiling_or_without_glibc_symbols(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target/release").mkdir(parents=True)
            binary = self._write(root / "target/release", b"GLIBC_2.39\0GLIBC_2.34\0")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ARC_KERNEL_MAX_GLIBC", None)
                self.assertEqual(pk.find_kernel(root), binary)
            binary.write_bytes(elf())  # static / musl: no GLIBC_ strings at all
            self.assertEqual(pk.find_kernel(root), binary)

    def test_should_let_a_known_newer_platform_raise_the_ceiling(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target/release").mkdir(parents=True)
            binary = self._write(root / "target/release", b"GLIBC_2.43\0")
            with patch.dict(os.environ, {"ARC_KERNEL_MAX_GLIBC": "2.43"}):
                self.assertEqual(pk.find_kernel(root), binary)
