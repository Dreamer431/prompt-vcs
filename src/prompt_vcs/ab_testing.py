"""
A/B Testing module for prompt-vcs.

Provides functionality to compare different versions of prompts and analyze their effectiveness.
"""

import functools
import hashlib
import math
import random
import re
import threading
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
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_MIN_SAMPLES_PER_VARIANT = 5
_CONFIDENCE_THRESHOLD = 0.95
_ZERO_VARIANCE_ABS_TOLERANCE = 1e-15


def _validate_storage_identifier(value: str, field_name: str) -> None:
    """Validate identifiers that are later used in local storage paths."""
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if value in {".", ".."} or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} may only contain letters, numbers, '.', '_' and '-'")


@dataclass
class ABTestVariant:
    """Represents a single variant in an A/B test."""
    version: str
    weight: float = 1.0
    description: str = ""
    
    def __post_init__(self):
        _validate_storage_identifier(self.version, "Variant version")
        try:
            self.weight = float(self.weight)
        except (TypeError, ValueError) as exc:
            raise ValueError("Weight must be a finite number") from exc
        if not math.isfinite(self.weight) or self.weight < 0:
            raise ValueError("Weight must be a finite non-negative number")


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
        _validate_storage_identifier(self.name, "Experiment name")
        _validate_storage_identifier(self.prompt_id, "Prompt ID")
        if not self.variants:
            # Default to v1 vs v2
            self.variants = [
                ABTestVariant(version="v1", weight=1.0),
                ABTestVariant(version="v2", weight=1.0),
            ]
        versions = [variant.version for variant in self.variants]
        if len(versions) != len(set(versions)):
            raise ValueError("Variant versions must be unique")
        if self.get_total_weight() <= 0:
            raise ValueError("At least one variant must have a positive weight")
    
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
        if user_id is not None:
            # Deterministic selection based on user_id hash
            digest = hashlib.sha256(f"{self.name}:{user_id}".encode()).digest()
            hash_value = int.from_bytes(digest[:8], "big")
            threshold = (hash_value / 2**64) * total_weight
        else:
            # Random selection
            threshold = random.random() * total_weight
        
        cumulative = 0.0
        for variant in self.variants:
            cumulative += variant.weight
            if threshold < cumulative:
                return variant
        
        return next(variant for variant in reversed(self.variants) if variant.weight > 0)


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

    def __post_init__(self) -> None:
        _validate_storage_identifier(self.experiment_name, "Experiment name")
        _validate_storage_identifier(self.variant_version, "Variant version")
        _validate_storage_identifier(self.prompt_id, "Prompt ID")
        if self.score is not None:
            self.score = float(self.score)
            if not math.isfinite(self.score) or not 0.0 <= self.score <= 1.0:
                raise ValueError("Score must be a finite number between 0.0 and 1.0")
        if self.latency_ms is not None:
            self.latency_ms = float(self.latency_ms)
            if not math.isfinite(self.latency_ms) or self.latency_ms < 0:
                raise ValueError("Latency must be a finite non-negative number")
    
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
            score_str = f"{stats.avg_score:.3f}" if stats.avg_score is not None else "N/A"
            latency_str = f"{stats.avg_latency_ms:.1f}ms" if stats.avg_latency_ms is not None else "N/A"
            lines.append(f"  {version}: count={stats.count}, avg_score={score_str}, avg_latency={latency_str}")
        
        if self.winner:
            lines.append("-" * 40)
            lines.append(f"Winner: {self.winner} (confidence: {self.confidence:.1%})")
        
        return "\n".join(lines)


# Global lock that serialises lockfile mutations during A/B prompt resolution.
# This ensures that concurrent calls from different threads don't interfere
# with each other's variant selection.
_lockfile_mutation_lock = threading.Lock()


@contextmanager
def _lockfile_override(prompt_manager: Any, prompt_id: str, version: str):
    """
    Thread-safe context manager that temporarily injects a version into the
    PromptManager lockfile for a single prompt resolution, then restores it.

    Uses a module-level lock so concurrent A/B calls don't stomp each other.
    """
    with _lockfile_mutation_lock:
        # Load before overriding; otherwise get_prompt() can reload from disk
        # and discard the selected variant on the first request.
        prompt_manager.load_lockfile()
        saved = prompt_manager._lockfile.copy()
        saved_loaded = prompt_manager._lockfile_loaded
        prompt_manager._lockfile = {**saved, prompt_id: version}
        prompt_manager._lockfile_loaded = True
        try:
            yield
        finally:
            prompt_manager._lockfile = saved
            prompt_manager._lockfile_loaded = saved_loaded


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
        # When True, __exit__ will not auto-save the record.
        # ABTestPromptResult sets this so the caller can save after calling
        # .record() with the outcome data, avoiding a duplicate write.
        self._suppress_autosave: bool = False

    def __enter__(self) -> "ABTestExperiment":
        self.variant = self.config.select_variant(self.user_id)
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._record and not self._suppress_autosave:
            self.manager.save_record(self._record)
    
    def get_prompt(self, **kwargs: Any) -> str:
        """
        Get the prompt for the selected variant.

        Returns the rendered prompt string.
        """
        if not self.variant:
            raise RuntimeError("Must be used within context manager")

        prompt_manager = get_manager()

        # Resolve against the selected version while serialising access to the
        # shared PromptManager lockfile.
        with _lockfile_override(prompt_manager, self.config.prompt_id, self.variant.version):
            rendered = prompt_manager.get_prompt(self.config.prompt_id, **kwargs)
        
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

        if score is not None:
            score = float(score)
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError("Score must be between 0.0 and 1.0 and finite")
        
        self._record.output = output
        self._record.score = score
        self._record.latency_ms = (time.time() - self.start_time) * 1000 if self.start_time else None
        self._record.metadata = metadata


def _determine_winner(
    variant_stats: dict[str, "ABTestStats"],
) -> tuple[Optional[str], Optional[float]]:
    """
    Determine the winning variant and a confidence value.

    Uses Welch's two-sample t-test when SciPy is installed. For large samples
    without SciPy, it uses a normal approximation to Welch's statistic. A
    winner is only returned at or above the configured confidence threshold.

    Returns ``(None, None)`` when:
    - Fewer than 2 variants have scored records.
    - Fewer than two variants meet the minimum sample size.
    - The best variant does not strictly outperform the next best.
    """
    scored = [
        (version, stats)
        for version, stats in variant_stats.items()
        if stats.avg_score is not None
        and len(stats.scores) >= _MIN_SAMPLES_PER_VARIANT
    ]

    if len(scored) < 2:
        return None, None

    scored.sort(key=lambda item: item[1].avg_score or 0.0, reverse=True)
    best_ver, best_stats = scored[0]
    _, second_stats = scored[1]

    best_mean = best_stats.avg_score
    second_mean = second_stats.avg_score
    if best_mean is None or second_mean is None or best_mean <= second_mean:
        return None, None

    def sample_variance(values: list[float]) -> float:
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values) / (len(values) - 1)

    best_variance = sample_variance(best_stats.scores)
    second_variance = sample_variance(second_stats.scores)

    # Identical observations with different means are deterministically
    # separated and should not be sent to scipy, which emits precision warnings.
    if math.isclose(
        best_variance,
        0.0,
        abs_tol=_ZERO_VARIANCE_ABS_TOLERANCE,
    ) and math.isclose(
        second_variance,
        0.0,
        abs_tol=_ZERO_VARIANCE_ABS_TOLERANCE,
    ):
        return best_ver, 1.0

    p_value: Optional[float] = None
    try:
        from scipy import stats as scipy_stats  # type: ignore[import]

        _, scipy_p_value = scipy_stats.ttest_ind(
            best_stats.scores,
            second_stats.scores,
            equal_var=False,
        )
        if math.isfinite(float(scipy_p_value)):
            p_value = float(scipy_p_value)
    except ImportError:
        pass

    if p_value is None:
        # The normal approximation is only used for sufficiently large groups.
        if min(len(best_stats.scores), len(second_stats.scores)) < 30:
            return None, None
        standard_error = math.sqrt(
            best_variance / len(best_stats.scores)
            + second_variance / len(second_stats.scores)
        )
        if math.isclose(
            standard_error,
            0.0,
            abs_tol=_ZERO_VARIANCE_ABS_TOLERANCE,
        ):
            return best_ver, 1.0
        z_score = (best_mean - second_mean) / standard_error
        p_value = math.erfc(abs(z_score) / math.sqrt(2.0))

    # Compare the best variant with every alternative conservatively.
    adjusted_p_value = min(1.0, p_value * (len(scored) - 1))
    confidence = 1.0 - adjusted_p_value
    if confidence < _CONFIDENCE_THRESHOLD:
        return None, None

    return best_ver, min(1.0, confidence)


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
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root
        self._experiments: dict[str, ABTestConfig] = {}
        self._records: dict[str, list[ABTestRecord]] = {}
        self._storage: Optional["ABTestStorage"] = None

    @classmethod
    def get_instance(cls, project_root: Optional[Path] = None) -> "ABTestManager":
        """Get or create the singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls(project_root)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._instance_lock:
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
        _validate_storage_identifier(name, "Experiment name")
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
        _validate_storage_identifier(name, "Experiment name")
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
        _validate_storage_identifier(experiment_name, "Experiment name")
        return self._get_storage().load_records(experiment_name)
    
    def analyze(self, experiment_name: str) -> ABTestResult:
        """
        Analyze results for an experiment.
        
        Returns:
            ABTestResult with statistics and winner determination
        """
        _validate_storage_identifier(experiment_name, "Experiment name")
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
        
        # Determine winner using Welch's two-sample t-test (via scipy) when
        # available, falling back to a Wilson score interval approximation.
        winner, confidence = _determine_winner(variant_stats)
        
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
    if len(weights) != len(variants):
        raise ValueError("Number of weights must match number of variants")
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
                prompt_manager = get_manager()
                # Use thread-safe lockfile override so concurrent calls don't
                # interfere with each other's variant selection.
                with _lockfile_override(prompt_manager, prompt_id, exp.variant.version):
                    result = func(*args, **kwargs)

                # Create a wrapper that allows recording
                return ABTestPromptResult(
                    prompt=result,
                    experiment=exp,
                )
        
        return wrapper  # type: ignore
    
    return decorator


class ABTestPromptResult(str):
    """
    Wrapper for prompt result that allows recording A/B test outcomes.
    
    Behaves like a string but also provides a record() method.
    """
    
    def __new__(
        cls,
        prompt: str,
        experiment: ABTestExperiment,
    ) -> "ABTestPromptResult":
        result = super().__new__(cls, prompt)
        result._experiment = experiment
        result._saved = False
        # Tell the experiment not to auto-save when the context manager exits —
        # we will save exactly once when the caller calls .record().
        result._experiment._suppress_autosave = True
        # Manually create the record since we didn't use get_prompt()
        result._experiment._record = ABTestRecord(
            experiment_name=experiment.config.name,
            variant_version=experiment.variant.version,
            prompt_id=experiment.config.prompt_id,
            inputs={},
            rendered_prompt=prompt,
            user_id=experiment.user_id,
        )
        return result
    
    def __repr__(self) -> str:
        return f"ABTestPromptResult({super().__repr__()})"
    
    def record(
        self,
        output: Optional[str] = None,
        score: Optional[float] = None,
        **metadata: Any,
    ) -> None:
        """Record the result of this prompt execution."""
        if self._saved:
            raise RuntimeError("This A/B test result has already been recorded")
        self._experiment.record(output=output, score=score, **metadata)
        self._experiment.manager.save_record(self._experiment._record)
        self._saved = True
