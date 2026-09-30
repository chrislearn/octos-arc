原始性能报告及证据已从临时工作树迁入此目录，六个原始文件保持逐字节一致。

- [原始报告](report.md)
- [原始复审记录](review.md)
- [已实施的改进与验证](../v15-performance-implementation-20260930/report.md)
- [工作树清理与恢复记录](../v15-performance-implementation-20260930/worktree-cleanup.json)

原始报告、JSON 和脚本中的旧绝对路径是历史证据，保留原样。旧工作树已经删除，原始报告内部的旧代码链接不再可直接打开；当前实现和 derived-tests 在主工作区。历史检查的 `passed` 描述当时的复算结果，不是要求新代码继续复现已修复的缺陷。

原始源码、未提交修改及忽略文件已保存在恢复快照中。Git 快照为 `521d265cc03724410c4b2a28921c08f37d9a1be2`，由 `codex/archive-hackathon-derived-specs-20260930` 分支保留；完整文件归档位置和 SHA-256 见恢复记录。重跑历史 audit.py 时应使用恢复的历史源码作为 `--source`，不能使用已修复的主工作区来复现旧缺陷。

此前 Sheet 后台补跑已随用户要求清理工作树而停止，退出码为 130。其输出和日志仍保留在主工作区的 `arc/arc-output/v15-sheet-isolated-20260930-182910`，不能把这次中止记录视为完整验收通过。
