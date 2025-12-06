"""
Demo application showing prompt-vcs usage.

Run this after:
1. pip install -e .
2. pvcs init
3. pvcs scaffold examples/
"""

from prompt_vcs import p, prompt


def demo_inline_mode():
    """Demonstrate inline mode with p() function."""
    print("=== Inline Mode Demo ===\n")
    
    # Simple greeting - will use default unless locked
    greeting = p("user_greeting", "你好 {{ name }}，欢迎使用本系统！", name="开发者")
    print(f"Greeting: {greeting}\n")
    
    # Farewell message
    farewell = p("farewell", "再见，{{ name }}！期待再次见到你。", name="开发者")
    print(f"Farewell: {farewell}\n")


def demo_decorator_mode():
    """Demonstrate decorator mode with @prompt."""
    print("=== Decorator Mode Demo ===\n")
    
    @prompt(id="system_core", default_version="v1")
    def get_system_prompt(role: str, language: str):
        """
        你是一个乐于助人的 AI 助手。
        你扮演的角色是：{{ role }}
        请使用 {{ language }} 回复用户。
        """
        pass
    
    system = get_system_prompt(role="技术顾问", language="中文")
    print(f"System Prompt:\n{system}\n")
    
    @prompt(id="chat_template")
    def get_chat_template(context: str, question: str):
        """
        根据以下上下文回答问题：
        
        上下文：{{ context }}
        
        问题：{{ question }}
        """
        pass
    
    chat = get_chat_template(
        context="Python 是一种高级编程语言。",
        question="Python 是什么？"
    )
    print(f"Chat Template:\n{chat}\n")


def main():
    print("\n" + "=" * 50)
    print("  prompt-vcs Demo")
    print("=" * 50 + "\n")
    
    demo_inline_mode()
    demo_decorator_mode()
    
    print("=" * 50)
    print("  Demo Complete!")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
