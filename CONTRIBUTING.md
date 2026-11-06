# 🤝 Contributing · 参与贡献

感谢关注 CSV Doctor。欢迎通过 **Issue** 反馈可复现问题，也欢迎提交聚焦的小型 Pull Request。

## 提交前

1. 阅读 [README](README.md) 与 [工程设计](docs/ENGINEERING.md)，确认需求符合轻量 CSV / XLSX 数据体检的定位。
2. 仅使用人工生成或已充分脱敏的样例。**不要上传真实业务数据、API 密钥或个人信息**。
3. 尽量先建立 Issue 讨论影响较大的变更，避免无关重构。

## 本地验证

建议 Python 3.11 / 3.12，并使用独立虚拟环境。

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

请遵循项目现有的模块职责：`app.py` 负责 UI，`src/` 负责读取、分析与清洗；涉及逻辑变化时，补充相应测试并更新文档。

## Pull Request 建议

说明 **问题背景 → 解决思路 → 影响文件 → 测试结果**。不要把未运行的检查写成通过，也不要附带真实用户数据。

项目采用 [MIT License](LICENSE)。
