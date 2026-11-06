# 🗒️ Changelog · 版本记录

本项目采用简洁的更新记录，区分已经实现的功能与未来计划。首次公开发布和版本标签仍以 GitHub 仓库实际状态为准。

## Unreleased — v1.0 本地候选版

### Added

- CSV / XLSX 上传、常见中文编码支持和 Excel 多工作表切换。
- 缺失值、整行重复记录与 IQR 统计异常分析。
- 透明可复现的启发式质量评分与深色交互式 Dashboard。
- 手动、非破坏式清洗预览；CSV 和 JSON 报告导出。
- 输入体积限制、CSV 公式触发文本保护、pytest 与 GitHub Actions 配置。

### Refined

- 修正缺失率图表标题，完善无缺失数据时的展示和中文说明。
- 补充页面与边界用例；本地开发报告为 **63 passed**，远程 CI 待首次执行。

### Planned（未实现）

- 可配置的列类型与业务规则校验。
- 更多文件解析选项与可访问性优化。

详情见 [README](README.md) 和 [工程设计](docs/ENGINEERING.md)。
