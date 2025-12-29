"""
Tests for A/B testing module.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from prompt_vcs.ab_testing import (
    ABTestConfig,
    ABTestManager,
    ABTestRecord,
    ABTestResult,
    ABTestVariant,
    ab_test,
)
from prompt_vcs.ab_storage import ABTestStorage


class TestABTestVariant:
    """Tests for ABTestVariant."""
    
    def test_create_variant(self):
        variant = ABTestVariant(version="v1", weight=1.0)
        assert variant.version == "v1"
        assert variant.weight == 1.0
    
    def test_negative_weight_raises(self):
        with pytest.raises(ValueError):
            ABTestVariant(version="v1", weight=-1.0)


class TestABTestConfig:
    """Tests for ABTestConfig."""
    
    def test_create_config(self):
        config = ABTestConfig(
            name="test_exp",
            prompt_id="greeting",
            variants=[
                ABTestVariant("v1", weight=1.0),
                ABTestVariant("v2", weight=1.0),
            ],
        )
        assert config.name == "test_exp"
        assert config.prompt_id == "greeting"
        assert len(config.variants) == 2
    
    def test_default_variants(self):
        config = ABTestConfig(name="test", prompt_id="greeting")
        assert len(config.variants) == 2
        assert config.variants[0].version == "v1"
        assert config.variants[1].version == "v2"
    
    def test_total_weight(self):
        config = ABTestConfig(
            name="test",
            prompt_id="greeting",
            variants=[
                ABTestVariant("v1", weight=1.0),
                ABTestVariant("v2", weight=2.0),
            ],
        )
        assert config.get_total_weight() == 3.0
    
    def test_select_variant_random(self):
        config = ABTestConfig(
            name="test",
            prompt_id="greeting",
            variants=[
                ABTestVariant("v1", weight=1.0),
                ABTestVariant("v2", weight=1.0),
            ],
        )
        
        # Run multiple times to ensure both variants are selected
        versions_seen = set()
        for _ in range(100):
            variant = config.select_variant()
            versions_seen.add(variant.version)
        
        assert "v1" in versions_seen
        assert "v2" in versions_seen
    
    def test_select_variant_deterministic(self):
        config = ABTestConfig(
            name="test",
            prompt_id="greeting",
            variants=[
                ABTestVariant("v1", weight=1.0),
                ABTestVariant("v2", weight=1.0),
            ],
        )
        
        # Same user_id should always get same variant
        variant1 = config.select_variant(user_id="user123")
        variant2 = config.select_variant(user_id="user123")
        assert variant1.version == variant2.version


class TestABTestStorage:
    """Tests for ABTestStorage."""
    
    def test_save_and_load_experiment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ABTestStorage(Path(tmpdir))
            
            config = ABTestConfig(
                name="test_exp",
                prompt_id="greeting",
                description="Test experiment",
                variants=[
                    ABTestVariant("v1", weight=1.0),
                    ABTestVariant("v2", weight=2.0),
                ],
            )
            
            storage.save_experiment(config)
            loaded = storage.load_experiment("test_exp")
            
            assert loaded is not None
            assert loaded.name == "test_exp"
            assert loaded.prompt_id == "greeting"
            assert len(loaded.variants) == 2
            assert loaded.variants[0].weight == 1.0
            assert loaded.variants[1].weight == 2.0
    
    def test_list_experiments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ABTestStorage(Path(tmpdir))
            
            # Create multiple experiments
            for i in range(3):
                config = ABTestConfig(name=f"exp_{i}", prompt_id=f"prompt_{i}")
                storage.save_experiment(config)
            
            experiments = storage.list_experiments()
            assert len(experiments) == 3
    
    def test_save_and_load_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ABTestStorage(Path(tmpdir))
            
            # Save multiple records
            for i in range(5):
                record = ABTestRecord(
                    experiment_name="test_exp",
                    variant_version="v1",
                    prompt_id="greeting",
                    inputs={"name": f"User{i}"},
                    rendered_prompt=f"Hello User{i}",
                    score=0.8,
                )
                storage.save_record(record)
            
            records = storage.load_records("test_exp")
            assert len(records) == 5
    
    def test_get_record_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ABTestStorage(Path(tmpdir))
            
            for i in range(10):
                record = ABTestRecord(
                    experiment_name="test_exp",
                    variant_version="v1",
                    prompt_id="greeting",
                    inputs={},
                    rendered_prompt="Hello",
                )
                storage.save_record(record)
            
            count = storage.get_record_count("test_exp")
            assert count == 10


class TestABTestManager:
    """Tests for ABTestManager."""
    
    def setup_method(self):
        ABTestManager.reset()
    
    def test_singleton(self):
        manager1 = ABTestManager.get_instance()
        manager2 = ABTestManager.get_instance()
        assert manager1 is manager2
    
    def test_create_and_get_experiment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ABTestManager(Path(tmpdir))
            
            config = ABTestConfig(name="test", prompt_id="greeting")
            manager.create_experiment(config)
            
            loaded = manager.get_experiment("test")
            assert loaded is not None
            assert loaded.name == "test"
    
    def test_analyze_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ABTestManager(Path(tmpdir))
            
            config = ABTestConfig(name="test", prompt_id="greeting")
            manager.create_experiment(config)
            
            result = manager.analyze("test")
            assert result.total_records == 0
    
    def test_analyze_with_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ABTestManager(Path(tmpdir))
            
            config = ABTestConfig(
                name="test",
                prompt_id="greeting",
                variants=[
                    ABTestVariant("v1", weight=1.0),
                    ABTestVariant("v2", weight=1.0),
                ],
            )
            manager.create_experiment(config)
            
            # Add records for v1 (higher scores)
            for _ in range(10):
                record = ABTestRecord(
                    experiment_name="test",
                    variant_version="v1",
                    prompt_id="greeting",
                    inputs={},
                    rendered_prompt="Hello",
                    score=0.9,
                )
                manager.save_record(record)
            
            # Add records for v2 (lower scores)
            for _ in range(10):
                record = ABTestRecord(
                    experiment_name="test",
                    variant_version="v2",
                    prompt_id="greeting",
                    inputs={},
                    rendered_prompt="Hi",
                    score=0.6,
                )
                manager.save_record(record)
            
            result = manager.analyze("test")
            assert result.total_records == 20
            assert result.winner == "v1"
            assert result.variant_stats["v1"].avg_score == pytest.approx(0.9)
            assert result.variant_stats["v2"].avg_score == pytest.approx(0.6)
