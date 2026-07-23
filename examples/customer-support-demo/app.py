"""A deterministic customer-support demo for prompt-vcs.

The demo only renders prompts and a clearly labelled mock response. It does not
call an external LLM and therefore needs no API key or network access.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from prompt_vcs import get_manager, p


PROJECT_ROOT = Path(__file__).resolve().parent


def configure_prompt_project(project_root: Path = PROJECT_ROOT) -> None:
    """Point prompt-vcs at this example instead of the repository root."""
    get_manager().set_project_root(project_root)


def build_support_prompt(customer_name: str, issue: str, tone: str) -> str:
    """Render the currently locked support-reply prompt."""
    return p(
        "support_reply",
        customer_name=customer_name,
        issue=issue,
        tone=tone,
    )


def build_ticket_summary(customer_name: str, issue: str, channel: str) -> str:
    """Render the currently locked ticket-summary prompt."""
    return p(
        "ticket_summary",
        customer_name=customer_name,
        issue=issue,
        channel=channel,
    )


def make_mock_response(customer_name: str, issue: str) -> str:
    """Return deterministic demo data; this is not an LLM-generated response."""
    return (
        f"您好，{customer_name}！我们已记录“{issue}”。"
        "请先在订单页查看最新物流节点；若 24 小时内仍无更新，请通过订单页联系人工客服。"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prompt-vcs 客服场景测试项目")
    parser.add_argument("--name", default="小林", help="客户姓名")
    parser.add_argument("--issue", default="包裹三天没有物流更新", help="客户问题")
    parser.add_argument("--tone", default="专业", help="期望回复语气")
    parser.add_argument("--channel", default="在线客服", help="工单来源渠道")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_prompt_project()

    print("=== 当前锁定版本生成的 Prompt ===")
    print(build_support_prompt(args.name, args.issue, args.tone))
    print()
    print("=== 工单摘要 ===")
    print(build_ticket_summary(args.name, args.issue, args.channel))
    print()
    print("=== 模拟模型响应（固定演示数据，不调用真实 API）===")
    print(make_mock_response(args.name, args.issue))


if __name__ == "__main__":
    main()
