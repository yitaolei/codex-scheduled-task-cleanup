# Codex 定时任务旧记录问题：技术排查说明

## 用途

当默认清理脚本失败、ChatGPT/Codex 更新后数据库结构变化，或者旧 run 已归档但重启后仍出现在左侧栏时，使用这份说明进行排查。

## 已知状态层

### 1. Automation definition

常见路径：

```text
~/.codex/automations/<automation-id>/automation.toml
```

这里保存真正的循环定时任务，例如：

- `id`
- `name`
- `status`
- `rrule`
- target
- execution environment

**左侧栏出现很多同名条目，并不能证明存在很多个 automation。**

首先应该确认真正的 automation definition 到底有几条。

### 2. Session index

常见路径：

```text
~/.codex/session_index.jsonl
```

一个 recurring schedule 每运行一次，都可能生成一个新的独立 session，因此可能出现很多：

- 相同 `thread_name`
- 不同 UUID
- 不同 `updated_at`

默认情况下，应该按 `updated_at` 保留最新 session。

### 3. Thread state DB

常见路径：

```text
~/.codex/state_5.sqlite
```

其中 `threads` 表曾观察到这些字段：

- `id`
- `rollout_path`
- `archived`
- `archived_at`
- `name`
- `thread_source`
- `project_id`

有一种关键故障状态是：

- `archived = 1`
- rollout 已经位于 `archived_sessions/...jsonl`

但这个 thread **仍然显示在 Desktop 左侧栏**。

这说明 thread archive 本身并不是唯一状态源。

### 4. Desktop app DB

目前观察到的候选路径：

```text
~/.codex/sqlite/codex.db
~/.codex/sqlite/codex-dev.db
```

脚本会寻找同时包含下面两个表的数据库：

```text
automation_runs
local_thread_catalog
```

曾观察到的 `automation_runs.status` 包括：

```text
IN_PROGRESS
PENDING_REVIEW
ACCEPTED
ARCHIVED
```

ChatGPT/Codex Desktop 自己正常执行归档时，会把对应 automation run 转为 `ARCHIVED`，并可能把 `archived_reason` 设置为 `auto`。

### 5. Local sidebar catalog

Desktop App 还维护一份：

```text
local_thread_catalog
```

正常归档 thread 时，App 会把该 thread 从 catalog 移除，并增加 catalog revision。

如果通过某条不完整路径只归档了 thread 文件，却没有触发 Desktop 的 side effects，catalog 就可能变成 stale 状态。

## 为什么 `codex archive <UUID>` 可能不够

Codex CLI 可以成功完成 session archive，同时更新 thread state。

但 Desktop Electron 层仍可能保留：

```text
automation_runs.status = PENDING_REVIEW
```

以及：

```text
local_thread_catalog
```

里的旧记录。

于是会出现：

1. archived rollout 文件已经存在；
2. `threads.archived = 1`；
3. 但是左侧栏仍然显示旧的 scheduled run。

本项目的清理脚本会在 exact-title 验证、automation-ID 验证和数据库备份以后，把这些状态同步完成。

## ChatGPT/Codex 更新后怎么办

如果脚本提示 schema changed：

1. 不要强行修改；
2. 先只读查看表名和 `PRAGMA table_info(...)`；
3. 如有需要，检查当前 App 自带的 app-server JSON schema；
4. 如果新版本已经提供完整的官方 archive API，应优先改用官方 API；
5. 如果仍然需要修复 Desktop side effects，必须先确认新版本实际行为，再更新脚本；
6. 更新脚本后重新做模拟测试。

## 这个项目不会做什么

它不会：

- 删除真正的 recurring schedule；
- 永久删除 archived chats；
- 绕过登录认证；
- 导出用户 cookie / token；
- 修改其他无关 Codex 项目历史；
- 使用固定屏幕坐标自动点击。
