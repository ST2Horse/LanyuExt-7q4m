"""检查真实文件行为、特殊路径及命令行输出。"""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lanyuext import DEFAULT_NOEXT_LABEL, main, scan_directory


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "中文 空格"
        self.root.mkdir()
        for name, content in {"A.TXT": b"abc", "b.txt": b"12", "README": b"x", ".env": b"yz", "archive.tar.gz": b"1234"}.items():
            (self.root / name).write_bytes(content)
        (self.root / "nested").mkdir()
        (self.root / "nested" / "code.py").write_bytes(b"123456")

    def test_grouping_and_no_changes(self):
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        report = scan_directory(self.root)
        self.assertEqual((report["total_files"], report["total_bytes"]), (5, 12))
        groups = {r["extension"]: (r["files"], r["bytes"]) for r in report["groups"]}
        self.assertEqual(groups, {".txt": (2, 5), ".gz": (1, 4), DEFAULT_NOEXT_LABEL: (2, 3)})
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_recursive_and_real_custom_parameter(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main([str(self.root), "--recursive", "--lanyu-noext-label", "NO_SUFFIX", "--json"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual((report["total_files"], report["total_bytes"]), (6, 18))
        self.assertEqual(report["no_extension_label"], "NO_SUFFIX")
        self.assertIn("NO_SUFFIX", [r["extension"] for r in report["groups"]])
        self.assertNotIn(DEFAULT_NOEXT_LABEL, [r["extension"] for r in report["groups"]])

    def test_missing_and_file_path(self):
        with self.assertRaises(FileNotFoundError):
            scan_directory(self.root / "missing")
        with self.assertRaises(NotADirectoryError):
            scan_directory(self.root / "A.TXT")

    def test_invalid_group_name(self):
        for label in ("", "  ", ".txt", "BAD\nLABEL"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                scan_directory(self.root, noext_label=label)

    def test_empty_directory(self):
        empty = self.root / "empty"
        empty.mkdir()
        report = scan_directory(empty)
        self.assertEqual((report["total_files"], report["total_bytes"], report["groups"]), (0, 0, []))

    def test_permission_problem_is_not_silent(self):
        with patch("lanyuext.os.scandir", side_effect=PermissionError("拒绝访问")):
            report = scan_directory(self.root)
        self.assertEqual(len(report["errors"]), 1)
        stdout = io.StringIO()
        with patch("lanyuext.os.scandir", side_effect=PermissionError("拒绝访问")), contextlib.redirect_stdout(stdout):
            self.assertEqual(main([str(self.root)]), 1)
        self.assertIn("结果不完整", stdout.getvalue())

    def test_symbolic_link_is_skipped(self):
        link = self.root / "loop"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("本机不允许创建测试符号链接")
        report = scan_directory(self.root, recursive=True)
        self.assertEqual(report["total_files"], 6)
        self.assertEqual(report["skipped_links"], 1)

    @unittest.skipUnless(os.name == "nt", "仅在Windows检查目录连接")
    def test_windows_directory_junction_is_skipped(self):
        link = self.root / "junction_loop"
        quote = lambda path: "'" + str(path).replace("'", "''") + "'"
        command = f"New-Item -ItemType Junction -Path {quote(link)} -Target {quote(self.root)} | Out-Null"
        completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True)
        if completed.returncode:
            self.skipTest("本机不允许创建测试目录连接")
        try:
            report = scan_directory(self.root, recursive=True)
            self.assertEqual(report["total_files"], 6)
            self.assertEqual(report["skipped_links"], 1)
        finally:
            # 仅删除新建的连接本身，不递归删除目标目录。
            link.rmdir()


if __name__ == "__main__":
    unittest.main()
