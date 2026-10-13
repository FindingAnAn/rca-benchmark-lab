"""Read a declared CSV per system without assuming its future schema"""

import shutil
from pathlib import Path

import pandas as pd

from src.domain.contracts import timestamp_seconds


class CsvLogAdapter:
    """Map timestamp/text columns and attach the system declared in configuration"""

    def read(
        self, root: Path, sources: list[dict], output: Path, max_rows: int
    ) -> pd.DataFrame:
        """Preserve original CSVs and parse only configured columns

        Args:
            root: Local Downloads folder selected by RCA_LOG_ROOT.
            sources: Filename, system_id and timestamp/text mapping per CSV.
            output: New immutable raw snapshot directory.
            max_rows: Maximum parsed rows across all files.
        Returns:
            Canonical log records; text is never copied into HTML or operational logs.
        Raises:
            ValueError: Missing fields, invalid time or exceeded row budget.
        """
        output.mkdir(parents=True, exist_ok=False)
        batches = []
        total_rows = 0
        if len({Path(source["file"]).name for source in sources}) != len(sources):
            raise ValueError("Each source needs a distinct CSV basename")
        for source in sources:
            path = (root / source["file"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("Log file must stay within RCA_LOG_ROOT")
            shutil.copy2(path, output / path.name)
            record_offset = 0
            for batch in pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                chunksize=10000,
                encoding=source.get("encoding", "utf-8-sig"),
                sep=source.get("delimiter", ","),
            ):
                total_rows += len(batch)
                if total_rows > max_rows:
                    raise ValueError("Log row budget exceeded; partition input files")
                time_column = source.get("timestamp_column", "timestamp")
                text_column = source.get("text_column", "text")
                if not {time_column, text_column} <= set(batch):
                    raise ValueError(
                        f"Configure timestamp/text columns for {path.name}"
                    )
                rows = pd.DataFrame(
                    {
                        "timestamp": [
                            timestamp_seconds(
                                value,
                                source.get("time_unit", "iso"),
                                source.get("timezone", "Asia/Ho_Chi_Minh"),
                            )
                            for value in batch[time_column]
                        ],
                        "text": batch[text_column].tolist(),
                        "system_id": source["system_id"],
                        "entity_id": (
                            batch[source["entity_column"]].tolist()
                            if source.get("entity_column")
                            else "system"
                        ),
                        "source_file": path.name,
                        "source_record": range(
                            record_offset + 1, record_offset + len(batch) + 1
                        ),
                        "source_timezone": source.get("timezone", "Asia/Ho_Chi_Minh"),
                        "expected_cdr_service_id": str(
                            source.get("cdr_service_id", "")
                        ),
                    }
                )
                batches.append(rows)
                record_offset += len(batch)
        return pd.concat(batches, ignore_index=True) if batches else pd.DataFrame()
