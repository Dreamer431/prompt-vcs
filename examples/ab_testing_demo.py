"""
A/B Testing Demo for prompt-vcs.

This example demonstrates how to use the A/B testing features to compare
different versions of prompts.

Run this after:
1. pip install -e .
2. pvcs init
"""

from prompt_vcs import p, ab_test, ABTestManager, ABTestConfig, ABTestVariant


def demo_context_manager_mode():
    """
    Demonstrate A/B testing using context manager.
    
    This is the most flexible approach, giving you full control over
    the experiment flow.
    """
    print("=" * 50)
    print("  A/B Testing: Context Manager Mode")
    print("=" * 50 + "\n")
    
    # 1. Create an experiment
    manager = ABTestManager.get_instance()
    
    config = ABTestConfig(
        name="greeting_experiment",
        prompt_id="user_greeting",
        description="Testing different greeting styles",
        variants=[
            ABTestVariant("v1", weight=1.0, description="Formal greeting"),
            ABTestVariant("v2", weight=1.0, description="Casual greeting"),
        ],
    )
    manager.create_experiment(config)
    print(f"Created experiment: {config.name}")
    print(f"  Prompt ID: {config.prompt_id}")
    print(f"  Variants: v1 (50%), v2 (50%)")
    print()
    
    # 2. Run the experiment multiple times
    print("Running 10 experiments...\n")
    
    for i in range(10):
        user_id = f"user_{i}"  # Use user_id for consistent bucketing
        
        with manager.experiment("greeting_experiment", user_id=user_id) as exp:
            # Get the prompt (automatically selects variant)
            prompt = exp.get_prompt(name="Alice")
            
            # Simulate LLM response (in real usage, call your LLM here)
            response = f"AI response to: {prompt[:30]}..."
            
            # Simulate quality score (in real usage, evaluate the response)
            import random
            score = random.uniform(0.6, 1.0)
            
            # Record the result
            exp.record(output=response, score=score)
            
            print(f"  User {i}: {exp.variant.version} → score={score:.2f}")
    
    print()
    
    # 3. Analyze results
    result = manager.analyze("greeting_experiment")
    print("Analysis Results:")
    print(result.summary())
    print()


def demo_decorator_mode():
    """
    Demonstrate A/B testing using the @ab_test decorator.
    
    This is a simpler approach for basic use cases.
    """
    print("=" * 50)
    print("  A/B Testing: Decorator Mode")
    print("=" * 50 + "\n")
    
    # Define a function with A/B testing
    @ab_test("farewell_experiment", prompt_id="farewell", variants=["v1", "v2"])
    def get_farewell(name: str) -> str:
        return p("farewell", "再见，{name}！", name=name)
    
    # Run the experiment
    print("Running 5 experiments...\n")
    
    for i in range(5):
        result = get_farewell(name="Bob")
        print(f"  Run {i+1}: {result}")
        
        # Record result (the decorator returns a special object with record method)
        import random
        result.record(output="AI says goodbye", score=random.uniform(0.7, 1.0))
    
    # Analyze
    manager = ABTestManager.get_instance()
    analysis = manager.analyze("farewell_experiment")
    print("\nAnalysis Results:")
    print(analysis.summary())
    print()


def demo_cli_workflow():
    """
    Demonstrate the CLI workflow for A/B testing.
    
    These commands can be run from the terminal.
    """
    print("=" * 50)
    print("  A/B Testing: CLI Workflow")
    print("=" * 50 + "\n")
    
    print("CLI commands available:\n")
    print("  # Create an experiment")
    print("  pvcs ab create greeting_test user_greeting --variants v1,v2\n")
    
    print("  # List all experiments")
    print("  pvcs ab list\n")
    
    print("  # View experiment status")
    print("  pvcs ab status greeting_test\n")
    
    print("  # Manually record a result")
    print("  pvcs ab record greeting_test v1 --score 0.8\n")
    
    print("  # Analyze results")
    print("  pvcs ab analyze greeting_test\n")
    
    print("  # Clear experiment records")
    print("  pvcs ab clear greeting_test --yes\n")


def main():
    print("\n" + "=" * 50)
    print("  prompt-vcs A/B Testing Demo")
    print("=" * 50 + "\n")
    
    demo_context_manager_mode()
    demo_decorator_mode()
    demo_cli_workflow()
    
    print("=" * 50)
    print("  Demo Complete!")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
