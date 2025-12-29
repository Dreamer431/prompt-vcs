"""
A/B Testing module for prompt-vcs.

Provides functionality to compare different versions of prompts and analyze their effectiveness.
"""

import functools
import hashlib
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from prompt_vcs.manager import get_manager

if TYPE_CHECKING:
    from prompt_vcs.ab_storage import ABTestStorage


F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ABTestVariant:
    """Represents a single variant in an A/B test."""
    version: str
    weight: float = 1.0
    description: str = ""
    
    def __post_init__(self):
        if self.weight < 0:
            raise ValueError("Weight must be non-negative")


@dataclass
class ABTestConfig:
    """Configuration for an A/B test experiment."""
    name: str
    prompt_id: str
    variants: list[ABTestVariant] = field(default_factory=list)
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    
    def __post_init__(self):
        if not self.variants:
            # Default to v1 vs v2
            self.variants = [
                ABTestVariant(version="v1", weight=1.0),
                ABTestVariant(version="v2", weight=1.0),
            ]
    
    def get_total_weight(self) -> float:
        """Get total weight of all variants."""
        return sum(v.weight for v in self.variants)
    
    def select_variant(self, user_id: Optional[str] = None) -> ABTestVariant:
        """
        Select a variant based on weights.
        
        If user_id is provided, the selection is deterministic for that user
        (consistent bucketing). Otherwise, random selection is used.
        """
        total_weight = self.get_total_weight()
        if total_weight == 0:
            return self.variants[0]
        
        if user_id:
            # Deterministic selection based on user_id hash
            hash_value = int(hashlib.md5(f"{self.name}:{user_id}".encode()).hexdigest(), 16)
            threshold = (hash_value % 10000) / 10000.0 * total_weight
        else:
            # Random selection
            threshold = random.random() * total_weight
        
        cumulative = 0.0
        for variant in self.variants:
            cumulative += variant.weight
            if threshold <= cumulative:
                return variant
        
        return self.variants[-1]


@dataclass
class ABTestRecord:
    """Record of a single A/B test invocation."""
    experiment_name: str
    variant_version: str
    prompt_id: str
    inputs: dict[str, Any]
    rendered_prompt: str
    output: Optional[str] = None
    score: Optional[float] = None
    latency_ms: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "experiment_name": self.experiment_name,
            "variant_version": self.variant_version,
            "prompt_id": self.prompt_id,
            "inputs": self.inputs,
            "rendered_prompt": self.rendered_prompt,
            "output": self.output,
            "score": self.score,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ABTestRecord":
        """Create from dictionary."""
        data = data.copy()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class ABTestStats:
    """Statistics for a single variant."""
    version: str
    count: int = 0
    avg_score: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    scores: list[float] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    
    def add_record(self, record: ABTestRecord) -> None:
        """Add a record to the statistics."""
        self.count += 1
        if record.score is not None:
            self.scores.append(record.score)
            self.avg_score = sum(self.scores) / len(self.scores)
        if record.latency_ms is not None:
            self.latencies.append(record.latency_ms)
            self.avg_latency_ms = sum(self.latencies) / len(self.latencies)


@dataclass
class ABTestResult:
    """Analysis result for an A/B test experiment."""
    experiment_name: str
    prompt_id: str
    total_records: int
    variant_stats: dict[str, ABTestStats] = field(default_factory=dict)
    winner: Optional[str] = None
    confidence: Optional[float] = None
    
    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"A/B Test Results: {self.experiment_name}",
            f"Prompt ID: {self.prompt_id}",
            f"Total Records: {self.total_records}",
            "-" * 40,
        ]
        
        for version, stats in self.variant_stats.items():
            score_str = f"{stats.avg_score:.3f}" if stats.avg_score else "N/A"
            latency_str = f"{stats.avg_latency_ms:.1f}ms" if stats.avg_latency_ms else "N/A"
            lines.append(f"  {version}: count={stats.count}, avg_score={score_str}, avg_latency={latency_str}")
        
        if self.winner:
            lines.append("-" * 40)
            lines.append(f"Winner: {self.winner} (confidence: {self.confidence:.1%})")
        
        return "\n".join(lines)


class ABTestExperiment:
    """Context manager for running an A/B test experiment."""
    
    def __init__(
        self,
        config: ABTestConfig,
        manager: "ABTestManager",
        user_id: Optional[str] = None,
    ):
        self.config = config
        self.manager = manager
        self.user_id = user_id
        self.variant: Optional[ABTestVariant] = None
        self.start_time: Optional[float] = None
        self._record: Optional[ABTestRecord] = None
    
    def __enter__(self) -> "ABTestExperiment":
        self.variant = self.config.select_variant(self.user_id)
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._record:
            self.manager.save_record(self._record)
    
    def get_prompt(self, **kwargs: Any) -> str:
        """
        Get the prompt for the selected variant.
        
        Returns the rendered prompt string.
        """
        if not self.variant:
            raise RuntimeError("Must be used within context manager")
        
        prompt_manager = get_manager()
        
        # Temporarily switch to the selected version
        old_lockfile = prompt_manager._lockfile.copy()
        prompt_manager._lockfile[self.config.prompt_id] = self.variant.version
        
        try:
            rendered = prompt_manager.get_prompt(self.config.prompt_id, **kwargs)
        finally:
            prompt_manager._lockfile = old_lockfile
        
        # Create record
        self._record = ABTestRecord(
            experiment_name=self.config.name,
            variant_version=self.variant.version,
            prompt_id=self.config.prompt_id,
            inputs=kwargs,
            rendered_prompt=rendered,
            user_id=self.user_id,
        )
        
        return rendered
    
    def record(
        self,
        output: Optional[str] = None,
        score: Optional[float] = None,
        **metadata: Any,
    ) -> None:
        """
        Record the result of this experiment run.
        
        Args:
            output: The LLM output (optional)
            score: Quality score (0-1, optional)
            **metadata: Additional metadata to store
        """
        if not self._record:
            raise RuntimeError("Must call get_prompt() first")
        
        self._record.output = output
        self._record.score = score
        self._record.latency_ms = (time.time() - self.start_time) * 1000 if self.start_time else None
        self._record.metadata = metadata


class ABTestManager:
    """
    Singleton manager for A/B testing experiments.
    
    Example:
        # Create an experiment
        manager = ABTestManager.get_instance()
        config = ABTestConfig(
            name="greeting_test",
            prompt_id="user_greeting",
            variants=[
                ABTestVariant("v1", weight=1.0),
                ABTestVariant("v2", weight=1.0),
            ]
        )
        manager.create_experiment(config)
        
        # Run experiment
        with manager.experiment("greeting_test") as exp:
            prompt = exp.get_prompt(name="Alice")
            response = my_llm.generate(prompt)
            exp.record(output=response, score=0.8)
        
        # Analyze results
        result = manager.analyze("greeting_test")
        print(result.summary())
    """
    
    _instance: Optional["ABTestManager"] = None
    
    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root
        self._experiments: dict[str, ABTestConfig] = {}
        self._records: dict[str, list[ABTestRecord]] = {}
        self._storage: Optional["ABTestStorage"] = None
    
    @classmethod
    def get_instance(cls, project_root: Optional[Path] = None) -> "ABTestManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(project_root)
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None
    
    def _get_storage(self) -> "ABTestStorage":
        """Get or create the storage instance."""
        if self._storage is None:
            from prompt_vcs.ab_storage import ABTestStorage
            
            if self._project_root is None:
                prompt_manager = get_manager()
                self._project_root = prompt_manager.project_root
            
            self._storage = ABTestStorage(self._project_root)
        return self._storage
    
    def create_experiment(self, config: ABTestConfig) -> None:
        """Create or update an experiment."""
        self._experiments[config.name] = config
        self._get_storage().save_experiment(config)
    
    def get_experiment(self, name: str) -> Optional[ABTestConfig]:
        """Get an experiment by name."""
        if name not in self._experiments:
            config = self._get_storage().load_experiment(name)
            if config:
                self._experiments[name] = config
        return self._experiments.get(name)
    
    def list_experiments(self) -> list[ABTestConfig]:
        """List all experiments."""
        return self._get_storage().list_experiments()
    
    @contextmanager
    def experiment(
        self,
        name: str,
        user_id: Optional[str] = None,
    ):
        """
        Context manager for running an experiment.
        
        Args:
            name: Experiment name
            user_id: User ID for consistent bucketing
            
        Yields:
            ABTestExperiment instance
        """
        config = self.get_experiment(name)
        if not config:
            raise ValueError(f"Experiment '{name}' not found")
        
        exp = ABTestExperiment(config, self, user_id)
        with exp:
            yield exp
    
    def save_record(self, record: ABTestRecord) -> None:
        """Save a test record."""
        if record.experiment_name not in self._records:
            self._records[record.experiment_name] = []
        self._records[record.experiment_name].append(record)
        self._get_storage().save_record(record)
    
    def get_records(self, experiment_name: str) -> list[ABTestRecord]:
        """Get all records for an experiment."""
        return self._get_storage().load_records(experiment_name)
    
    def analyze(self, experiment_name: str) -> ABTestResult:
        """
        Analyze results for an experiment.
        
        Returns:
            ABTestResult with statistics and winner determination
        """
        config = self.get_experiment(experiment_name)
        if not config:
            raise ValueError(f"Experiment '{experiment_name}' not found")
        
        records = self.get_records(experiment_name)
        
        # Calculate stats per variant
        variant_stats: dict[str, ABTestStats] = {}
        for variant in config.variants:
            variant_stats[variant.version] = ABTestStats(version=variant.version)
        
        for record in records:
            if record.variant_version in variant_stats:
                variant_stats[record.variant_version].add_record(record)
        
        # Determine winner (simple comparison for now)
        winner = None
        confidence = None
        scored_variants = [
            (v, s) for v, s in variant_stats.items() 
            if s.avg_score is not None and s.count >= 5
        ]
        
        if len(scored_variants) >= 2:
            scored_variants.sort(key=lambda x: x[1].avg_score, reverse=True)
            best = scored_variants[0]
            second = scored_variants[1]
            
            if best[1].avg_score > second[1].avg_score:
                winner = best[0]
                # Simple confidence based on score difference and sample size
                diff = best[1].avg_score - second[1].avg_score
                min_count = min(best[1].count, second[1].count)
                confidence = min(0.99, 0.5 + diff * min(min_count / 20, 1.0) * 0.5)
        
        return ABTestResult(
            experiment_name=experiment_name,
            prompt_id=config.prompt_id,
            total_records=len(records),
            variant_stats=variant_stats,
            winner=winner,
            confidence=confidence,
        )


def ab_test(
    experiment_name: str,
    prompt_id: Optional[str] = None,
    variants: Optional[list[str]] = None,
    weights: Optional[list[float]] = None,
) -> Callable[[F], F]:
    """
    Decorator for A/B testing a prompt function.
    
    The decorated function should return a rendered prompt string.
    Call `.record(output, score)` on the result to record outcomes.
    
    Example:
        @ab_test("greeting_test", prompt_id="user_greeting", variants=["v1", "v2"])
        def get_greeting(name: str) -> str:
            return p("user_greeting", name=name)
        
        # Usage
        prompt = get_greeting(name="Alice")
        response = llm.generate(prompt)
        prompt.record(output=response, score=0.9)
    
    Args:
        experiment_name: Name of the experiment
        prompt_id: Prompt ID (defaults to experiment_name)
        variants: List of version strings (defaults to ["v1", "v2"])
        weights: List of weights for each variant (defaults to equal weights)
    """
    if variants is None:
        variants = ["v1", "v2"]
    if weights is None:
        weights = [1.0] * len(variants)
    if prompt_id is None:
        prompt_id = experiment_name
    
    variant_objs = [
        ABTestVariant(version=v, weight=w) 
        for v, w in zip(variants, weights)
    ]
    
    def decorator(func: F) -> F:
        # Ensure experiment exists
        manager = ABTestManager.get_instance()
        config = manager.get_experiment(experiment_name)
        if not config:
            config = ABTestConfig(
                name=experiment_name,
                prompt_id=prompt_id,
                variants=variant_objs,
            )
            manager.create_experiment(config)
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> "ABTestPromptResult":
            with manager.experiment(experiment_name) as exp:
                # Override the lockfile for this call
                prompt_manager = get_manager()
                old_lockfile = prompt_manager._lockfile.copy()
                prompt_manager._lockfile[prompt_id] = exp.variant.version
                
                try:
                    result = func(*args, **kwargs)
                finally:
                    prompt_manager._lockfile = old_lockfile
                
                # Create a wrapper that allows recording
                return ABTestPromptResult(
                    prompt=result,
                    experiment=exp,
                )
        
        return wrapper  # type: ignore
    
    return decorator


class ABTestPromptResult:
    """
    Wrapper for prompt result that allows recording A/B test outcomes.
    
    Behaves like a string but also provides a record() method.
    """
    
    def __init__(self, prompt: str, experiment: ABTestExperiment):
        self._prompt = prompt
        self._experiment = experiment
        # Manually create the record since we didn't use get_prompt()
        self._experiment._record = ABTestRecord(
            experiment_name=experiment.config.name,
            variant_version=experiment.variant.version,
            prompt_id=experiment.config.prompt_id,
            inputs={},
            rendered_prompt=prompt,
            user_id=experiment.user_id,
        )
    
    def __str__(self) -> str:
        return self._prompt
    
    def __repr__(self) -> str:
        return f"ABTestPromptResult({self._prompt!r})"
    
    def record(
        self,
        output: Optional[str] = None,
        score: Optional[float] = None,
        **metadata: Any,
    ) -> None:
        """Record the result of this prompt execution."""
        self._experiment.record(output=output, score=score, **metadata)
        # Manually save since we're outside the context manager
        self._experiment.manager.save_record(self._experiment._record)
