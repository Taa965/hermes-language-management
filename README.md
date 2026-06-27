# 零点零三 Hermes 语言管理

当前版本：`v0.1.0`

`zero-zero-three-hermes-language-management` 是一个面向 Hermes / Hermes fork 的本地化 skill。它让 Hermes agent 可以自动扫描用户可见文案，生成翻译计划，分批调用模型翻译，校验结果，安全写入源码或 locale，并保留回滚路径。

## 核心能力

- 确定性解析 `/zero-zero-three-hermes-language-management`、`/语言`、`/技能语言` 等快捷命令，裸命令默认 `zh-CN` 简体中文。
- 扫描 CLI、TUI、Web、gateway、tools 等用户可见文案。
- 基于 baseline 做 Hermes 更新后的增量检测。
- 生成风险分级 patch plan，保护命令、路径、URL、变量、模型 ID、provider ID。
- 将大翻译请求拆成小批次，并自动维护队列、进度和失败重试。
- 校验翻译结果的 JSON 结构、缺失 ID、占位符和保留 token。
- 安全应用低/中风险翻译，生成 `rollback.patch`。
- 生成并执行 i18n key 迁移计划，支持写入 locale 文件并替换源码 helper 调用。
- 检查多语言 locale key、占位符、空值和疑似未翻译文本。
- 扫描本地其他 skill 的用户可见输出文本并生成翻译批次。

## 仓库结构

```text
.
├── zero-zero-three-hermes-language-management/  # skill 本体
├── tests/fixtures/hermes-mini/                  # smoke test fixture
├── tests/smoke_test.py                          # 发布前测试
├── .github/workflows/ci.yml                     # CI
├── VERSION
├── RELEASE_NOTES.md
├── README.md
└── LICENSE
```

## 安装

把 skill 文件夹复制到 Hermes 可发现的 skills 目录：

```bash
git clone https://github.com/Taa965/hermes-language-management.git
mkdir -p ~/.hermes/skills
cp -R hermes-language-management/zero-zero-three-hermes-language-management ~/.hermes/skills/
```

如果你也希望本地 agent/Codex 发现它：

```bash
mkdir -p ~/.agents/skills ~/.codex/skills
cp -R hermes-language-management/zero-zero-three-hermes-language-management ~/.agents/skills/
cp -R hermes-language-management/zero-zero-three-hermes-language-management ~/.codex/skills/
```

安装 Hermes 快捷命令别名：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/install_hermes_language_aliases.py
```

安装或更新后，在 Hermes 中执行：

```text
/reload-skills
```

## 快速使用

在 Hermes 对话里直接调用：

```text
/zero-zero-three-hermes-language-management
```

裸命令默认等价于“扫描当前 Hermes 项目，目标语言简体中文，完成翻译、校验、应用和报告”。也可以显式指定语言：

```text
/语言 日文
/语言 韩文
/语言 繁体中文
```

本地其他 skill 输出文案的语言替换：

```text
/技能语言
/技能语言 日文
```

常用选项：

```text
/语言 只扫描
/语言 续跑
/语言 状态
/语言 i18n
/语言 高风险也改
```

## 短语使用

如果不想记命令，也可以直接对 Hermes 说这些短语：

```text
使用零点零三Hermes语言管理，把当前 Hermes 项目汉化成中文。
使用这个语言管理 skill，扫描并汉化当前项目。
汉化当前 Hermes 项目，直接修改代码并生成回滚包。
把当前 Hermes 项目翻译成日文。
把当前 Hermes 项目翻译成韩文。
只扫描当前 Hermes 项目中还没有本地化的英文，不要修改源码。
继续上一次汉化任务，从断点续跑。
查看当前汉化任务进度。
把本地其他 skill 的输出文案也汉化成中文。
把本地其他 skill 的输出文案翻译成日文。
使用 i18n key 迁移模式，把硬编码文案迁移到 locale 文件。
```

等价快捷命令：

```text
/zero-zero-three-hermes-language-management
/语言
/语言 日文
/语言 只扫描
/语言 续跑
/语言 状态
/语言 i18n
/技能语言
/技能语言 日文
```

## 命令行流程

从 Hermes repo 根目录运行：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/run_localization_pipeline.py . \
  --target-locale zh-CN \
  --target-language "Simplified Chinese" \
  --mode both \
  --out-dir localization-work
```

查看进度：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/localization_status.py \
  --work-dir localization-work
```

翻译批次队列和失败重试：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/manage_translation_batches.py \
  --batches-dir localization-work/batches \
  --retry-failed \
  --next 3
```

合并已校验翻译：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/merge_translation_results.py \
  --batches-dir localization-work/batches \
  --out localization-work/merged-translation-results.json \
  --require-validation \
  --update-status
```

应用翻译并生成回滚包：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/apply_translation_results.py \
  --repo . \
  --request localization-work/translation-request.json \
  --translations localization-work/merged-translation-results.json \
  --out localization-work/apply-report.json \
  --markdown localization-work/apply-report.md \
  --rollback-patch localization-work/rollback.patch \
  --apply \
  --max-risk medium
```

回滚检查和应用：

```bash
git apply --check localization-work/rollback.patch
git apply localization-work/rollback.patch
```

## 主要脚本

- `resolve_shortcut_command.py`: 确定性解析快捷命令、目标语言、模式和选项。
- `run_localization_pipeline.py`: 生成扫描、增量、patch plan、i18n plan、translation request 和批次目录。
- `manage_translation_batches.py`: 校验已有批次结果，选择下一批，并为失败或截断响应生成更小 retry 批次。
- `apply_translation_results.py`: 按已校验翻译结果安全替换源码文案并生成回滚 patch。
- `apply_i18n_migration.py`: 应用 i18n key 迁移计划，写入 locale 文件并替换源码 helper 调用。
- `localization_status.py`: 查看 pipeline、批次、应用结果和回滚包状态。

## i18n Key 迁移

生成迁移计划：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/generate_i18n_migration_plan.py \
  --input localization-work/localization-patch-plan.json \
  --namespace auto \
  --source-locale en \
  --target-locale zh-CN \
  --out localization-work/i18n-migration-plan.json \
  --markdown localization-work/i18n-migration-plan.md
```

在已有 i18n helper 的项目中应用迁移：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/apply_i18n_migration.py \
  --repo . \
  --plan localization-work/i18n-migration-plan.json \
  --translations localization-work/merged-translation-results.json \
  --locales-dir locales \
  --source-locale en \
  --target-locale zh-CN \
  --out localization-work/i18n-apply-report.json \
  --markdown localization-work/i18n-apply-report.md \
  --rollback-patch localization-work/i18n-rollback.patch \
  --apply \
  --max-risk medium
```

该执行器不会创造新的 i18n runtime。它只在项目已有 helper 约定时，把 locale key 写入 locale 文件，并把硬编码文案替换为类似 `t("key")` 的调用。

## 多语言一致性检查

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/check_i18n_consistency.py \
  --locales-dir locales \
  --source-locale en \
  --format markdown \
  --out i18n-consistency.md
```

CI 中可以阻断缺失 key、空值、占位符不一致：

```bash
python ~/.hermes/skills/zero-zero-three-hermes-language-management/scripts/check_i18n_consistency.py \
  --locales-dir locales \
  --source-locale en \
  --fail-on errors
```

## 发布前验证

```bash
python -m py_compile zero-zero-three-hermes-language-management/scripts/*.py
python tests/smoke_test.py
```

也可以运行 skill 结构校验：

```bash
python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py zero-zero-three-hermes-language-management
```

## 安全边界

- 默认保护命令、flags、URL、路径、provider/model/tool ID 和占位符。
- 默认跳过模型提示词、skill 指令、外部 provider 输出和高风险项。
- 写入源码前先生成可审计报告。
- `apply_translation_results.py --apply` 和 `apply_i18n_migration.py --apply` 会修改文件，同时生成回滚 patch。
- 不把真实密钥、私有 URL、用户数据写入 translation memory。

## 许可证

MIT License. See [LICENSE](LICENSE).
