# Release Checklist | 发布检查清单

本文档规范了每次版本发布前需要完成的检查步骤。

---

## 📋 发布前检查清单

### 1. 代码质量
- [ ] 运行 Lint 检查：`ruff check src/ tests/`
- [ ] 修复所有 Lint 错误
- [ ] 运行测试：`pytest tests/ -v`
- [ ] 确保所有测试通过
- [ ] 运行扩展检查：`npm --prefix vscode-extension test`
- [ ] 构建并检查发行包：`python -m build`、`twine check dist/*`

### 2. 版本号更新

**两处版本号必须同步更新：**

- [ ] 更新 `pyproject.toml` 中的 `version`
  ```toml
  version = "x.y.z"
  ```
- [ ] 更新 `src/prompt_vcs/__init__.py` 中的 `__version__`
  ```python
  __version__ = "x.y.z"
  ```
- [ ] **确认两处版本号一致！**

### 3. 文档更新
- [ ] 更新 `README.md`（英文）
  - 新功能说明
  - CLI 命令表格
  - 使用示例
- [ ] 更新 `README.zh-CN.md`（中文）
  - 保持与英文版同步
- [ ] 更新 `CHANGELOG.md`（如有）

### 4. Git 忽略检查
- [ ] 确认 `.gitignore` 包含所有运行时生成的文件
  - `.prompt_lock.json`
  - `prompts/`
  - `.prompt_ab/`
  - `__pycache__/`
  - `.pytest_cache/`

### 5. 提交规范
使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Type 类型：**
| Type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 代码重构 |
| `test` | 测试相关 |
| `chore` | 构建/工具链 |

**示例：**
```bash
git commit -m "feat(ab-testing): add A/B testing module (v0.5.0)"
```

---

## 🚀 发布流程

```bash
# 1. 确保代码通过检查
ruff check src/ tests/
python -m pytest tests/ -v
npm --prefix vscode-extension test
python -m build
twine check dist/*

# 2. 添加所有更改
git add .

# 3. 提交（使用规范格式）
git commit -m "feat: add new feature (vX.Y.Z)"

# 4. 打标签
git tag vX.Y.Z

# 5. 推送代码和标签
git push origin main
git push origin vX.Y.Z
# 或一次性推送
git push origin main --tags

# 6. 推送 tag 后由 GitHub Actions Trusted Publishing 发布到 PyPI
```

---

## 📝 版本号规则

遵循 [Semantic Versioning](https://semver.org/)：

- **MAJOR (X)**: 不兼容的 API 变更
- **MINOR (Y)**: 向后兼容的功能新增
- **PATCH (Z)**: 向后兼容的 Bug 修复

**示例：**
- `0.4.0` → `0.5.0`：新增 A/B 测试功能
- `0.5.0` → `0.5.1`：修复 Bug
- `0.5.1` → `1.0.0`：正式发布稳定版

---

## ⚡ 快速命令

```bash
# PowerShell 检查
ruff check src/ tests/
python -m pytest tests/ -v
npm --prefix vscode-extension test

# 查看当前版本
python -c "from prompt_vcs import __version__; print(__version__)"

# 查看最近 tag（PowerShell）
git tag --sort=-creatordate | Select-Object -First 5
```
