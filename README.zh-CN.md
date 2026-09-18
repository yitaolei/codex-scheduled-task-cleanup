# Codex 定时任务旧记录清理工具

[English](README.md)

这是一个可复用的 **ChatGPT Skill + macOS 清理工具**，专门解决这样的问题：

> Codex 里明明只有 **1 个 recurring schedule（循环定时任务）**，但每次运行以后都会生成一个新的历史会话，久而久之，同名的旧任务会一直堆在 ChatGPT/Codex 项目左侧栏里。

更麻烦的是，有时即使已经执行了 `codex archive <UUID>`，甚至重启 ChatGPT App，旧记录仍然会继续显示。

## 问题的真正原因

Codex 的定时任务实际上涉及至少三层状态：

1. **Automation definition**：真正的循环定时任务本身；
2. **Run thread/session**：每一次定时运行产生的独立会话；
3. **Desktop state**：ChatGPT/Codex Desktop 自己维护的 automation review / sidebar catalog 状态。

因此：

**左侧栏出现 10 条同名记录，并不代表你有 10 个 schedule。**

很可能实际上只有 1 个 schedule，但已经运行了 10 次，因此留下了 10 个历史 session。

而且只归档 session 本身还可能不够，因为 Desktop 本地数据库里仍然可能保留：

- `automation_runs.status = PENDING_REVIEW`
- `local_thread_catalog` 里的旧 thread

这就是为什么“已经 archive 了，但左侧栏还在”。

## 这个工具会做什么

清理脚本会：

- 默认只做 **dry-run**，先告诉你准备清理哪些记录；
- 只匹配**完全相同的标题**，避免误伤其他会话；
- 默认永远保留最新 1 条；
- 写入前自动备份 SQLite 数据库；
- 使用 Codex CLI 归档旧 session；
- 把旧的 `automation_runs` 状态同步为 `ARCHIVED`；
- 从 `local_thread_catalog` 移除已经归档的旧记录；
- 验证最新那一条没有被归档；
- 可以反复运行，不会重复破坏状态。

## 使用要求

- macOS
- ChatGPT Desktop / Codex 本地会话
- Python 3
- ChatGPT App 内置的 Codex CLI，或者系统 `PATH` 中可用的 `codex`

## 快速使用

### 第一步：一定先 dry-run

```bash
python3 scripts/cleanup_codex_scheduled_runs.py \
  --title "我的定时任务标题" \
  --automation-id "automation-id"
```

这一步不会修改任何东西，只会显示：

- 找到多少条同名 session；
- 哪一条会保留；
- 哪些旧记录准备归档。

### 第二步：确认无误后执行

```bash
python3 scripts/cleanup_codex_scheduled_runs.py \
  --title "我的定时任务标题" \
  --automation-id "automation-id" \
  --apply
```

完成后，请：

**⌘ + Q 完全退出 ChatGPT App，然后重新打开。**

正常情况下，左侧栏就只会保留最新的一条。

## 自动清理

如果你的 schedule 每天会运行多次，可以让系统在每次运行后几分钟自动清理旧记录。

例如：定时任务每天约在 06:00、11:00、16:00 运行，可以设置清理在 06:10、11:10、16:10：

```bash
python3 scripts/install_launchagent.py \
  --cleanup-script "$(pwd)/scripts/cleanup_codex_scheduled_runs.py" \
  --title "我的定时任务标题" \
  --automation-id "automation-id" \
  --times "06:10,11:10,16:10"
```

请根据你自己的 schedule 修改时间，不要照抄示例时间。

## 安全设计

这个项目刻意做得比较保守：

- **不会删除 recurring schedule**；
- **不会永久删除 archived chats**；
- 默认 dry-run；
- 只做 exact-title 匹配；
- 可额外验证 automation ID；
- 至少保留 1 条 session；
- 修改 SQLite 前先备份；
- 数据库结构不符合预期时直接停止；
- 不读取或导出登录 cookie / token；
- 不采用固定坐标自动点击 UI 的方式；
- 执行完还会做状态验证。

## 为什么不能只用 `codex archive`？

因为在我们实际排查到的故障模式里：

1. session rollout 文件已经移动到 `~/.codex/archived_sessions/`；
2. `state_5.sqlite` 里该 thread 已经是 `archived=1`；
3. 但 ChatGPT/Codex Desktop 的 `automation_runs` 仍然是 `PENDING_REVIEW`；
4. `local_thread_catalog` 也仍然保留那条旧 thread；
5. 所以重启 App 后，左侧栏还是会显示旧记录。

正确处理必须把这几层状态同步起来。

更详细的技术排查过程见：

[references/diagnosis.zh-CN.md](references/diagnosis.zh-CN.md)

## ChatGPT Skill

仓库同时包含 `SKILL.md`，因此可以作为 ChatGPT Skill 使用。

如果你已经有打包好的 `skill.zip`，可以直接上传到 ChatGPT Skills；也可以用本仓库作为个人 Skill 的源文件。

## 兼容性提醒

这个工具基于 **2026 年 9 月 macOS ChatGPT Desktop / Codex 的实际本地结构**开发。

`state_5.sqlite`、`automation_runs`、`local_thread_catalog` 等属于内部实现，未来版本可能变化。因此每次 ChatGPT/Codex 大版本更新后，建议先使用 dry-run。

如果脚本发现 schema 不符合预期，它会停止，而不是猜测字段继续修改。

## License

MIT，见 [LICENSE](LICENSE)。
