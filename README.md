# LanyuExt-7q4m

一个按文件扩展名统计目录的小工具。可查看不同类型文件的数量和大小，也可把没有扩展名的文件单独归组。

只读取文件名及文件元信息，不读取文件内容、不修改被统计文件、不访问网络。保存报告时，只写入你指定的报告文件。

## 直接打开

Windows 下双击本目录中的 `打开工具.cmd`。选择文件夹，再点击“开始统计”。当前电脑已经具备运行环境。

也可以执行：

```powershell
python lanyuext.py --gui
```

需要 Python 3.10 或以上。命令行只用标准库；窗口需要 Tkinter。Windows 的常见 Python 安装通常包含 Tkinter，如使用精简环境，请先检查。

## 先用随附样例试一遍

选择本目录下的 `demo` 文件夹：

- 不勾选“包含子目录”：3个文件，分别归入 `.json`、`.txt`、`NOEXT_LY7Q4M`。
- 勾选“包含子目录”：5个文件，增加 `.py` 分组，`.txt` 分组变为2个文件。
- 把“无扩展名分组名称”改成 `NO_SUFFIX` 后重新统计：无扩展名文件的分组随之改名，文件数量不变。

文件大小按实际字节数计算；修改样例文件或换行格式会改变大小。

## 命令行使用

```powershell
python lanyuext.py demo
python lanyuext.py demo --recursive
python lanyuext.py demo --recursive --lanyu-noext-label NO_SUFFIX
python lanyuext.py demo --recursive --json
```

路径有空格时加引号：

```powershell
python lanyuext.py "D:\我的资料" --recursive
```

| 参数 | 真实作用 |
| --- | --- |
| `directory` | 要统计的文件夹路径 |
| `--recursive` | 包含子目录，默认不包含 |
| `--lanyu-noext-label 名称` | 改变无扩展名文件的分组名称，默认 `NOEXT_LY7Q4M` |
| `--json` | 将统计结果输出为 JSON |
| `--gui` | 打开窗口 |
| `--version` | 显示版本 |

`--lanyu-noext-label` 确实会改变报告中的分组名称，并非只供展示的装饰参数。分组名称不能为空、不能以点开头、不能含控制字符，以免与正常扩展名混淆。

## 统计规则

- 大小写相同的后缀合并：`.TXT` 与 `.txt` 都记为 `.txt`。
- 只取最后一段扩展名：`archive.tar.gz` 归入 `.gz`。
- `README`、`.env` 这类没有有效扩展名的文件，进入无扩展名分组。
- 文件大小是逻辑字节数，不是磁盘实际占用空间。
- Windows目录连接、符号链接等重解析点会跳过；云盘占位项也可能因此跳过。
- 硬链接按路径分别计数，不根据文件内容去重。
- 对无法读取的路径记录问题；报告不是某个时刻的完整目录快照，扫描过程中目录变化也可能影响结果。
- 命令行完成且没有读取问题时退出码为0；存在读取问题时为1；参数或输入目录错误时为2。

## 检查

```powershell
python -m unittest discover -s tests -v
```

测试使用独立的临时文件，覆盖中文及空格路径、大小写后缀、无扩展名文件、子目录、自定义分组、空目录、无效路径、读取错误，以及环境允许创建时的链接与目录连接。
