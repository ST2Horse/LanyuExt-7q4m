"""按扩展名统计文件数量与大小，使用 Python 标准库。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import stat
import sys
import threading


TOOL_NAME = "LanyuExt-7q4m"
VERSION = "0.1.0"
DEFAULT_NOEXT_LABEL = "NOEXT_LY7Q4M"


def validate_label(value: str) -> str:
    """避免无扩展名分组与正常后缀重名，或破坏输出格式。"""
    value = value.strip()
    if not value or value.startswith(".") or any(ord(c) < 32 for c in value):
        raise ValueError("分组名称不能为空、不能以点开头，也不能包含控制字符。")
    return value


def scan_directory(directory: str | Path, recursive: bool = False,
                   noext_label: str = DEFAULT_NOEXT_LABEL) -> dict:
    """只读取目录项和文件元信息，不读取文件内容，不跟随链接。"""
    noext_label = validate_label(noext_label)
    root = Path(directory).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"请选择文件夹：{root}")
    groups: dict[str, dict] = {}
    pending = [root]
    errors = []
    skipped_links = 0
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                        # Windows 目录连接、符号链接等重解析点都跳过。
                        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse_flag:
                            skipped_links += 1
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if recursive:
                                pending.append(Path(entry.path))
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        # 只取最后一段扩展名；没有有效扩展名的文件单独归组。
                        suffix = Path(entry.name).suffix.casefold()
                        if suffix in ("", "."):
                            suffix = noext_label
                        bucket = groups.setdefault(suffix, {"extension": suffix, "files": 0, "bytes": 0})
                        bucket["files"] += 1
                        bucket["bytes"] += info.st_size
                    except OSError as exc:
                        errors.append({"path": entry.path, "message": str(exc)})
        except OSError as exc:
            errors.append({"path": str(current), "message": str(exc)})

    ordered = sorted(groups.values(), key=lambda row: row["extension"].casefold())
    return {
        "tool": TOOL_NAME,
        "version": VERSION,
        "directory": str(root),
        "recursive": recursive,
        "no_extension_label": noext_label,
        "total_files": sum(row["files"] for row in ordered),
        "total_bytes": sum(row["bytes"] for row in ordered),
        "skipped_links": skipped_links,
        "errors": errors,
        "groups": ordered,
    }


def format_report(report: dict) -> str:
    lines = [f"{TOOL_NAME} {VERSION}", f"目录：{report['directory']}",
             f"包含子目录：{'是' if report['recursive'] else '否'}", "", "类型\t文件数\t大小（字节）"]
    lines += [f"{row['extension']}\t{row['files']}\t{row['bytes']}" for row in report["groups"]]
    lines += ["", f"合计：{report['total_files']} 个文件，{report['total_bytes']} 字节",
              f"跳过链接：{report['skipped_links']}；读取问题：{len(report['errors'])}"]
    if report["errors"]:
        lines.append("结果不完整，以下路径未能读取：")
        lines += [f"- {e['path']}：{e['message']}" for e in report["errors"]]
    return "\n".join(lines)


class DirectoryApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.root = root
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.result_queue = queue.Queue()
        self.report = None
        self.busy = False
        root.title(f"{TOOL_NAME} · 文件类型统计")
        root.geometry("850x590")
        root.minsize(700, 480)
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=28)
        main = ttk.Frame(root, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)

        ttk.Label(main, text="查看文件夹里的文件类型、数量和大小", font=("Microsoft YaHei UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(main, text="只读取文件名和大小，不修改文件；默认只统计当前文件夹。").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))
        self.directory = tk.StringVar()
        ttk.Entry(main, textvariable=self.directory).grid(row=2, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(main, text="选择文件夹", command=self.choose).grid(row=2, column=1)
        options = ttk.Frame(main)
        options.grid(row=3, column=0, columnspan=2, sticky="ew", pady=12)
        self.recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="包含子目录", variable=self.recursive).pack(side="left", padx=(0, 24))
        ttk.Label(options, text="无扩展名分组名称：").pack(side="left")
        self.label = tk.StringVar(value=DEFAULT_NOEXT_LABEL)
        ttk.Entry(options, textvariable=self.label, width=25).pack(side="left")
        actions = ttk.Frame(main)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.scan_button = ttk.Button(actions, text="开始统计", command=self.start)
        self.scan_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="保存报告（JSON）", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.details_button = ttk.Button(actions, text="查看读取问题", command=self.show_errors, state="disabled")
        self.details_button.pack(side="left")
        table_frame = ttk.Frame(main)
        table_frame.grid(row=5, column=0, columnspan=2, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_frame, columns=("type", "count", "bytes"), show="headings")
        for col, title, width in [("type", "类型", 260), ("count", "文件数", 130), ("bytes", "大小（字节）", 210)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w" if col == "type" else "e")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.status = tk.StringVar(value="选择一个文件夹后点击“开始统计”。")
        ttk.Label(main, textvariable=self.status, wraplength=760).grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def choose(self):
        path = self.filedialog.askdirectory(title="选择要统计的文件夹")
        if path:
            self.directory.set(path)

    def start(self):
        if self.busy:
            return
        directory = self.directory.get().strip()
        if not directory:
            self.messagebox.showerror("还没有选择文件夹", "请先选择文件夹。")
            return
        try:
            label = validate_label(self.label.get())
        except ValueError as exc:
            self.messagebox.showerror("分组名称不合适", str(exc))
            return
        self.busy = True
        self.report = None
        self.scan_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.details_button.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.status.set("正在统计，请稍候……")
        recursive = self.recursive.get()

        def worker():
            try:
                self.result_queue.put((True, scan_directory(directory, recursive, label)))
            except Exception as exc:
                self.result_queue.put((False, str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(60, self.poll)

    def poll(self):
        try:
            ok, result = self.result_queue.get_nowait()
        except queue.Empty:
            self.root.after(60, self.poll)
            return
        self.busy = False
        self.scan_button.configure(state="normal")
        if not ok:
            self.status.set("统计没有完成，请检查文件夹路径。")
            self.messagebox.showerror("无法统计", result)
            return
        self.report = result
        for row in result["groups"]:
            self.tree.insert("", "end", values=(row["extension"], row["files"], row["bytes"]))
        self.status.set(f"共 {result['total_files']} 个文件，{result['total_bytes']} 字节；跳过链接 {result['skipped_links']} 个，读取问题 {len(result['errors'])} 个。")
        self.save_button.configure(state="normal")
        if result["errors"]:
            self.details_button.configure(state="normal")

    def save(self):
        if self.report is None:
            return
        path = self.filedialog.asksaveasfilename(title="保存统计报告", defaultextension=".json", initialfile="lanyuext-report.json", filetypes=[("JSON报告", "*.json")])
        if path:
            try:
                Path(path).write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except OSError as exc:
                self.messagebox.showerror("保存失败", str(exc))
            else:
                self.status.set(f"报告已保存到：{path}")

    def show_errors(self):
        if self.report:
            self.messagebox.showinfo("读取问题", "\n".join(f"{e['path']}：{e['message']}" for e in self.report["errors"]) or "没有读取问题。")


def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{TOOL_NAME}：按文件扩展名统计数量和大小，只读取文件元信息。")
    parser.add_argument("directory", nargs="?", help="要统计的文件夹")
    parser.add_argument("--recursive", action="store_true", help="包含子目录，跳过符号链接和目录连接")
    parser.add_argument("--lanyu-noext-label", default=DEFAULT_NOEXT_LABEL, metavar="名称", help=f"设置无扩展名文件的分组名称，默认 {DEFAULT_NOEXT_LABEL}")
    parser.add_argument("--json", action="store_true", help="输出JSON报告")
    parser.add_argument("--gui", action="store_true", help="打开文件夹选择窗口")
    parser.add_argument("--version", action="version", version=f"{TOOL_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.gui:
        import tkinter as tk
        root = tk.Tk()
        DirectoryApp(root)
        root.mainloop()
        return 0
    if args.directory is None:
        parser.error("请提供文件夹路径，或使用 --gui 打开窗口。")
    try:
        report = scan_directory(args.directory, args.recursive, args.lanyu_noext_label)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    # 重定向报告时使用 UTF-8，终端输出保留系统自己的控制台编码。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
