from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import app


class CustomerSupportDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        shutil.copyfile(app.PROJECT_ROOT / "prompts.yaml", self.project_root / "prompts.yaml")

    def tearDown(self) -> None:
        app.configure_prompt_project()
        self.temp_dir.cleanup()

    def lock_versions(self, version: str) -> None:
        lockfile = {
            "support_reply": version,
            "ticket_summary": version,
        }
        (self.project_root / ".prompt_lock.json").write_text(
            json.dumps(lockfile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        app.configure_prompt_project(self.project_root)

    def test_v1_renders_customer_data(self) -> None:
        self.lock_versions("v1")

        rendered = app.build_support_prompt("小林", "包裹三天没有物流更新", "专业")

        self.assertIn("客户姓名：小林", rendered)
        self.assertIn("客户问题：包裹三天没有物流更新", rendered)
        self.assertIn("使用专业、清晰的语气", rendered)

    def test_v2_adds_security_guardrail(self) -> None:
        self.lock_versions("v2")

        rendered = app.build_support_prompt("小林", "退款尚未到账", "耐心")

        self.assertIn("工单优先级：普通", rendered)
        self.assertIn("不要提供密码或验证码", rendered)

    def test_mock_response_is_deterministic(self) -> None:
        response = app.make_mock_response("小林", "包裹三天没有物流更新")

        self.assertEqual(
            response,
            "您好，小林！我们已记录“包裹三天没有物流更新”。"
            "请先在订单页查看最新物流节点；若 24 小时内仍无更新，请通过订单页联系人工客服。",
        )


if __name__ == "__main__":
    unittest.main()
