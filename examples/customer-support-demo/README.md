# prompt-vcs 客服场景测试项目

这是一个可以离线运行的最小完整项目，用来验证当前仓库中的 `prompt-vcs` 是否能正常完成：

- 从 `prompts.yaml` 读取并渲染 Prompt；
- 使用 `.prompt_lock.json` 锁定 `v1`；
- 对比并切换 `v1`、`v2`；
- 运行 YAML Prompt 测试套件；
- 验证模拟回复是否满足规则；
- 用 Python 单元测试同时覆盖两个 Prompt 版本。

示例不会调用真实 LLM，也不需要 API Key。`app.py` 输出中的“模拟模型响应”是固定测试数据，不能视为模型效果测试。

## 为什么放在当前仓库内

建议位置就是现在的 `examples/customer-support-demo/`，而不是仓库外的新项目。

这样做的原因是：它属于当前库的可运行用例，可以直接验证尚未发布的本地源码，也能随代码变更一起回归测试；同时它位于独立子目录，不会把业务样例混入 `src/prompt_vcs` 核心包。

只有当你准备把客服样例继续开发成真实产品、需要独立发布或需要自己的 Git 历史时，才适合把它复制为仓库外的新项目。

## 环境要求

- Windows PowerShell
- Python 3.10 或更高版本

首次运行时，在仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
```

这会以可编辑模式安装当前源码。以后修改 `src/prompt_vcs` 后不必重复安装。

## 一条命令完成全部测试

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\customer-support-demo\run_all.ps1
```

脚本依次运行示例应用、YAML 测试套件、Python 单元测试、回复验证和版本差异检查。任何一步失败都会停止并返回非零退出码。

### 成功时的预期结果

输出较长，但应出现以下关键内容：

```text
[1/5] Run demo application
=== 当前锁定版本生成的 Prompt ===
客户姓名：小林
客户问题：包裹三天没有物流更新

[2/5] Run YAML prompt test suite
Total:   2
Passed:  2 +
Failed:  0 x
Pass Rate: 100.0%

[3/5] Run Python unit tests for v1 and v2
Ran 3 tests
OK

[4/5] Validate mock response
All validation rules passed!

[5/5] Show prompt diff between v1 and v2
Diff: support_reply (v1 → v2)

All checks passed.
```

表格边框、颜色符号和每项耗时可能因终端环境不同而略有差异；通过数量和最终结论应一致。

## 分步运行

先进入样例目录：

```powershell
Set-Location .\examples\customer-support-demo
```

### 1. 运行应用

```powershell
python -X utf8 .\app.py
```

也可以传入自定义参数：

```powershell
python -X utf8 .\app.py --name "王女士" --issue "退款五天仍未到账" --tone "耐心" --channel "电话"
```

预期：打印当前版本的完整 Prompt、工单摘要和明确标注的固定模拟回复，命令退出码为 `0`。

### 2. 查看当前锁定版本

```powershell
python -X utf8 -m prompt_vcs.cli status --project .
```

预期：

```text
support_reply   v1   ✓ Exists
ticket_summary  v1   ✓ Exists
```

### 3. 运行 Prompt 测试

```powershell
python -X utf8 -m prompt_vcs.cli test .\tests\prompt_suite.yaml --project . --verbose
```

预期：共 `2` 项测试，`2` 项通过，失败和错误均为 `0`。

仅运行冒烟测试：

```powershell
python -X utf8 -m prompt_vcs.cli test .\tests\prompt_suite.yaml --project . --tag smoke
```

### 4. 运行 Python 单元测试

```powershell
python -m unittest discover -s .\tests -p "test_*.py" -v
```

预期：`Ran 3 tests`，最终显示 `OK`。测试在临时目录中分别锁定 `v1` 和 `v2`，不会修改样例自己的锁文件。

### 5. 验证一条模拟回复

```powershell
$mockResponse = (Get-Content -LiteralPath .\tests\mock_response.txt -Encoding UTF8 -Raw).Trim()
python -X utf8 -m prompt_vcs.cli validate support_reply $mockResponse --config .\tests\response_validation.yaml
```

预期：3 条验证规则全部显示 `✓`，最后显示 `All validation rules passed!`。

### 6. 对比两个版本

```powershell
python -X utf8 -m prompt_vcs.cli diff support_reply v1 v2 --project .
```

预期：显示统一差异，其中 `v2` 新增“工单优先级”和“不要提供密码或验证码”等约束。

### 7. 手动切换到 v2

```powershell
python -X utf8 -m prompt_vcs.cli switch support_reply v2 --project .
python -X utf8 -m prompt_vcs.cli switch ticket_summary v2 --project .
python -X utf8 .\app.py
```

预期：应用输出中出现：

```text
工单优先级：普通
不要提供密码或验证码
【在线客服】小林：包裹三天没有物流更新（待客服处理）
```

测试完成后可恢复初始状态：

```powershell
python -X utf8 -m prompt_vcs.cli switch support_reply v1 --project .
python -X utf8 -m prompt_vcs.cli switch ticket_summary v1 --project .
```

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `app.py` | 最小业务程序，渲染两个 Prompt 并输出固定模拟回复 |
| `prompts.yaml` | `support_reply` 和 `ticket_summary` 的 v1/v2 定义 |
| `.prompt_lock.json` | 初始版本锁，两个 Prompt 均锁定为 v1 |
| `tests/prompt_suite.yaml` | `pvcs test` 使用的声明式测试套件 |
| `tests/response_validation.yaml` | `pvcs validate` 使用的输出验证规则 |
| `tests/mock_response.txt` | 一键脚本用于输出验证的 UTF-8 示例文本 |
| `tests/test_app.py` | 覆盖 v1、v2 和固定模拟响应的单元测试 |
| `run_all.ps1` | 一键运行全部检查 |

## 常见问题

如果出现 `No module named prompt_vcs`，说明当前仓库还没有安装，请回到仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
```

如果 PowerShell 阻止执行脚本，可继续使用文档中的分步命令，或者仅对本次命令使用前文的 `-ExecutionPolicy Bypass`。

如果测试显示 `Prompt ... is locked to missing version`，请检查 `.prompt_lock.json` 中的版本是否确实存在于 `prompts.yaml`。
