# Release Checklist | 发布检查清单

本文档用于 Python 包的新版本发布。推送版本标签后，
`.github/workflows/publish.yml` 会通过 PyPI Trusted Publishing 自动发布。

## 1. 发布内容确认

- [ ] 当前位于 `main`：`git branch --show-current`
- [ ] 工作区只包含本次发布内容：`git status --short`
- [ ] `CHANGELOG.md` 已包含本次版本、发布日期和主要变更
- [ ] `README.md` 与 `README.zh-CN.md` 已同步新功能、命令和示例
- [ ] `.gitignore` 已覆盖运行时和测试生成物
- [ ] GitHub CLI 已登录正确账号：`gh auth status`

VS Code 扩展使用独立版本号，不要求与 Python 包版本同步。

## 2. Python 版本号确认

以下两处必须完全一致：

- [ ] `pyproject.toml` 的 `project.version`
- [ ] `src/prompt_vcs/__init__.py` 的 `__version__`

PowerShell 检查：

```powershell
python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
python -c "from prompt_vcs import __version__; print(__version__)"
```

还需确认目标版本尚未出现在
[prompt-vcs 的 PyPI 发布历史](https://pypi.org/project/prompt-vcs/#history)。
PyPI 文件名不可覆盖，已经发布的版本号不能重复使用。

## 3. 发布级验证

首次运行前安装开发和扩展依赖：

```powershell
python -m pip install -e ".[dev]"
npm --prefix vscode-extension ci
```

执行统一发布验证：

```powershell
python scripts/verify.py --release
git diff --check
```

`--release` 必须覆盖并通过：

- [ ] Ruff：`src/`、`tests/`、`scripts/`
- [ ] 全部 Python 测试和 70% 覆盖率门槛
- [ ] 示例程序
- [ ] VS Code 扩展类型检查、测试和编译
- [ ] npm 高危依赖审计
- [ ] sdist 与 wheel 构建、Twine 元数据检查
- [ ] wheel 中的 `py.typed` 和意外文件检查
- [ ] 在临时虚拟环境安装 wheel、导入包并执行 `pvcs --help`

## 4. 提交与远程同步

提交信息使用 Conventional Commits，例如：

```powershell
git add <明确的文件列表>
git commit -m "chore(release): prepare vX.Y.Z"
```

提交后检查远程，避免覆盖其他人的工作：

```powershell
git fetch --prune origin
git status -sb
git rev-list --left-right --count origin/main...main
```

- [ ] 工作区干净
- [ ] `origin/main` 没有本地尚未合并的远程提交
- [ ] 本地和远程都不存在目标标签

```powershell
git tag --list vX.Y.Z
git ls-remote --tags origin refs/tags/vX.Y.Z
```

## 5. 先推送 main 并等待 CI

```powershell
git push origin main
gh run list --workflow CI --branch main --commit (git rev-parse HEAD)
```

- [ ] 找到本次提交对应的 CI run
- [ ] 使用 `gh run watch <run-id> --exit-status` 等待成功
- [ ] CI 未成功前不要创建或推送版本标签

## 6. 创建并推送单个版本标签

CI 成功后创建 annotated tag：

```powershell
git tag -a vX.Y.Z -m "prompt-vcs vX.Y.Z"
git push origin vX.Y.Z
```

不要使用 `git push --tags`，避免误推其他本地标签。

## 7. 监控 PyPI 发布

```powershell
gh run list --workflow "Publish to PyPI" --branch vX.Y.Z
gh run watch <run-id> --exit-status
```

- [ ] `Verify tag matches package version` 成功
- [ ] 测试、构建和 Twine 检查成功
- [ ] `Publish to PyPI` 成功
- [ ] PyPI 发布历史显示新版本及 wheel、sdist
- [ ] 从 PyPI 安装新版本并运行 `pvcs --help`

发布后验证：

```powershell
python -m pip index versions prompt-vcs
```

## 失败处理

- main CI 失败：修复后重新提交并推送，禁止推 tag。
- 发布工作流基础设施失败：修复配置后重跑工作流。
- 已推 tag 后发现代码缺陷：不要强制移动远程 tag；修复后发布新的补丁版本。
