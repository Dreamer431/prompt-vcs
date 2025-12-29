"""
Storage module for A/B testing data.

Uses local JSON files for persistence, following the Git-native philosophy.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from prompt_vcs.ab_testing import ABTestConfig, ABTestRecord, ABTestVariant


# Directory names
AB_TEST_DIR = ".prompt_ab"
EXPERIMENTS_DIR = "experiments"
RECORDS_DIR = "records"


class ABTestStorage:
    """
    Local file storage for A/B test data.
    
    Directory structure:
        .prompt_ab/
        ├── experiments/
        │   ├── greeting_test.json
        │   └── summary_test.json
        └── records/
            ├── greeting_test/
            │   ├── 2024-12-29.jsonl
            │   └── 2024-12-30.jsonl
            └── summary_test/
                └── 2024-12-29.jsonl
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root or Path.cwd()
        self._ab_dir = self._project_root / AB_TEST_DIR
        self._experiments_dir = self._ab_dir / EXPERIMENTS_DIR
        self._records_dir = self._ab_dir / RECORDS_DIR
    
    def _ensure_dirs(self) -> None:
        """Ensure all required directories exist."""
        self._experiments_dir.mkdir(parents=True, exist_ok=True)
        self._records_dir.mkdir(parents=True, exist_ok=True)
    
    def save_experiment(self, config: ABTestConfig) -> Path:
        """
        Save an experiment configuration.
        
        Args:
            config: The experiment configuration to save
            
        Returns:
            Path to the saved file
        """
        self._ensure_dirs()
        
        file_path = self._experiments_dir / f"{config.name}.json"
        
        data = {
            "name": config.name,
            "prompt_id": config.prompt_id,
            "description": config.description,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat(),
            "variants": [
                {
                    "version": v.version,
                    "weight": v.weight,
                    "description": v.description,
                }
                for v in config.variants
            ],
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return file_path
    
    def load_experiment(self, name: str) -> Optional[ABTestConfig]:
        """
        Load an experiment configuration by name.
        
        Args:
            name: Experiment name
            
        Returns:
            ABTestConfig or None if not found
        """
        file_path = self._experiments_dir / f"{name}.json"
        
        if not file_path.exists():
            return None
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        variants = [
            ABTestVariant(
                version=v["version"],
                weight=v.get("weight", 1.0),
                description=v.get("description", ""),
            )
            for v in data.get("variants", [])
        ]
        
        return ABTestConfig(
            name=data["name"],
            prompt_id=data["prompt_id"],
            description=data.get("description", ""),
            is_active=data.get("is_active", True),
            created_at=datetime.fromisoformat(data["created_at"]),
            variants=variants,
        )
    
    def list_experiments(self) -> list[ABTestConfig]:
        """
        List all experiment configurations.
        
        Returns:
            List of ABTestConfig objects
        """
        if not self._experiments_dir.exists():
            return []
        
        experiments = []
        for file_path in self._experiments_dir.glob("*.json"):
            config = self.load_experiment(file_path.stem)
            if config:
                experiments.append(config)
        
        return experiments
    
    def delete_experiment(self, name: str) -> bool:
        """
        Delete an experiment and all its records.
        
        Args:
            name: Experiment name
            
        Returns:
            True if deleted, False if not found
        """
        file_path = self._experiments_dir / f"{name}.json"
        records_path = self._records_dir / name
        
        deleted = False
        
        if file_path.exists():
            file_path.unlink()
            deleted = True
        
        if records_path.exists():
            import shutil
            shutil.rmtree(records_path)
            deleted = True
        
        return deleted
    
    def save_record(self, record: ABTestRecord) -> Path:
        """
        Save a test record to a daily JSONL file.
        
        Args:
            record: The record to save
            
        Returns:
            Path to the records file
        """
        self._ensure_dirs()
        
        # Create experiment-specific records directory
        exp_records_dir = self._records_dir / record.experiment_name
        exp_records_dir.mkdir(parents=True, exist_ok=True)
        
        # Use date-based file naming
        date_str = record.timestamp.strftime("%Y-%m-%d")
        file_path = exp_records_dir / f"{date_str}.jsonl"
        
        # Append to JSONL file
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        
        return file_path
    
    def load_records(
        self,
        experiment_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[ABTestRecord]:
        """
        Load records for an experiment.
        
        Args:
            experiment_name: Experiment name
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of ABTestRecord objects
        """
        exp_records_dir = self._records_dir / experiment_name
        
        if not exp_records_dir.exists():
            return []
        
        records = []
        
        for file_path in sorted(exp_records_dir.glob("*.jsonl")):
            # Parse date from filename
            try:
                file_date = datetime.strptime(file_path.stem, "%Y-%m-%d")
            except ValueError:
                continue
            
            # Apply date filters
            if start_date and file_date.date() < start_date.date():
                continue
            if end_date and file_date.date() > end_date.date():
                continue
            
            # Load records from file
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            record = ABTestRecord.from_dict(data)
                            
                            # Additional timestamp filtering
                            if start_date and record.timestamp < start_date:
                                continue
                            if end_date and record.timestamp > end_date:
                                continue
                            
                            records.append(record)
                        except (json.JSONDecodeError, KeyError, TypeError):
                            continue
        
        return records
    
    def get_record_count(self, experiment_name: str) -> int:
        """
        Get the total number of records for an experiment.
        
        Args:
            experiment_name: Experiment name
            
        Returns:
            Total record count
        """
        exp_records_dir = self._records_dir / experiment_name
        
        if not exp_records_dir.exists():
            return 0
        
        count = 0
        for file_path in exp_records_dir.glob("*.jsonl"):
            with open(file_path, "r", encoding="utf-8") as f:
                count += sum(1 for line in f if line.strip())
        
        return count
    
    def clear_records(self, experiment_name: str) -> int:
        """
        Clear all records for an experiment.
        
        Args:
            experiment_name: Experiment name
            
        Returns:
            Number of records cleared
        """
        exp_records_dir = self._records_dir / experiment_name
        
        if not exp_records_dir.exists():
            return 0
        
        count = self.get_record_count(experiment_name)
        
        import shutil
        shutil.rmtree(exp_records_dir)
        exp_records_dir.mkdir(parents=True, exist_ok=True)
        
        return count
