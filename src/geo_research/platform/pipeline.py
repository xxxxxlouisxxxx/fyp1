"""V0.1 offline orchestration; no collection, dbt, publication or source writes.

The legacy runner couples normalization and enrichment. Invalidated runs rebuild
both in a private snapshot rather than reseeding an old database. ``output`` is
a container for immutable run directories, not a database or publication target.
Review documents must expose kind, payload_json (or document_json/content_json),
and either status='completed' or a completed presentation.releases release_id.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, get_args
from uuid import uuid4

SCHEMA_VERSION = "platform-pipeline-0.1-scoped-guard-1"
ReviewStatus = Literal[
    "draft", "under_review", "approved", "rejected", "snoozed", "completed"
]
REVIEW_STATES = frozenset(get_args(ReviewStatus))


@dataclass(frozen=True)
class Stage:
    """Declared dependencies and actual execution boundary, not a paid job."""

    name: Literal["normalize", "evidence"]
    dependencies: tuple[str, ...]
    executor: str


STAGES = (
    Stage("normalize", (), "transform_all_raw.run"),
    Stage("evidence", ("normalize",), "transform_all_raw.run/enrich_database"),
)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _date(value: str | None) -> date | None:
    if value is None:
        return None
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("raw_date must be YYYY-MM-DD")
    return parsed


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _paths(project: Path, output: Path) -> tuple[Path, Path]:
    project, output = project.resolve(), output.resolve()
    if not project.is_dir():
        raise ValueError("project must be an existing directory")
    protected = [project / name for name in (
        "data/raw", "data/input", "data/warehouse", "src", "scripts",
        "config", "models", "macros", "tests",
    )]
    if _inside(project, output) or any(
        _inside(output, item.resolve()) for item in protected
    ):
        raise ValueError("output overlaps protected source inputs or warehouse")
    if output.exists() and not output.is_dir():
        raise ValueError("output must be a directory")
    # Reject existing databases anywhere in the requested output container.
    if output.exists() and any(output.glob("*.duckdb")):
        raise ValueError("output contains an existing warehouse")
    return project, output


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _snapshot(project: Path, raw_date: date | None) -> dict[str, Any]:
    raw = project / "data/raw"
    raw_files = _files(raw)
    for path in raw_files:
        if not _inside(path.resolve(), raw.resolve()):
            raise ValueError("raw symlink escapes source root")
    scoped = [path for path in raw_files if raw_date is None or
              path.relative_to(raw).parts[3:6] == tuple(
                  raw_date.strftime("%Y/%m/%d").split("/"))]
    registry_files = [path for path in _files(project / "config/registries")
                      if path.suffix == ".csv"]
    # Explicit allowlist: never load .env, profiles.yml or secret settings.
    code_files = sorted(set(
        [path for folder in ("scripts", "src/geo_research", "models", "macros")
         for path in _files(project / folder)
         if path.suffix in {".py", ".sql", ".yml", ".yaml"}]
        + [path for path in _files(project / "config")
           if path.name.endswith(".example.yaml")]
        + [project / name for name in ("dbt_project.yml", "pyproject.toml")
           if (project / name).is_file()]
    ))
    # Only the canonical baseline is authoritative in this scoped platform run.
    # The runner discovers all databases in its private copy; copying only this
    # baseline makes the declared provenance boundary its actual read boundary.
    baseline = project / "data/warehouse/geo_research.duckdb"
    provenance = [baseline] if baseline.is_file() else []
    guard = sorted(set(scoped + registry_files + code_files + provenance))
    checksums = {path: _hash(path) for path in guard}

    def hashes(paths: list[Path]) -> dict[str, str]:
        return {path.relative_to(project).as_posix(): checksums[path] for path in paths}

    groups: dict[str, Any] = {
              "input_hashes": hashes(scoped), "code_hashes": hashes(code_files),
              "registry_hashes": hashes(registry_files),
              "provenance_hashes": hashes(provenance)}
    groups["scope"] = {"project": str(project),
                       "raw_date": raw_date.isoformat() if raw_date else None,
                       "basis": "raw folder YYYY/MM/DD",
                       "provenance_basis": "canonical geo_research.duckdb only",
                       "guard_basis": (
                           "SHA256 selected raw, registries, allowlisted code and "
                           "canonical provenance; other raw/input/warehouse "
                           "metadata only"
                       )}
    groups["source_guard"] = hashes(guard)
    # Detect additions/deletions and ordinary mutation outside the content scope
    # without reading unrelated multi-gigabyte derived warehouses. This is NOT
    # a checksum guarantee for unselected input content.
    metadata_files = sorted(set(raw_files + _files(project / "data/warehouse")
                                + _files(project / "data/input")) - set(guard))
    groups["source_metadata_guard"] = {}
    for path in metadata_files:
        stat = path.stat()
        groups["source_metadata_guard"][path.relative_to(project).as_posix()] = {
            "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        }
    groups["compatibility_hash"] = _digest({
        "schema": SCHEMA_VERSION, "runtime": sys.version,
        **{key: value for key, value in groups.items()
           if key not in {"source_guard", "source_metadata_guard"}},
    })
    return groups


def _atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True,
                      indent=2, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _runner(project: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"_platform_offline_{uuid4().hex}", project / "scripts/transform_all_raw.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("offline runner is unavailable")
    module = importlib.util.module_from_spec(spec)
    old_path, old_bytecode = sys.path[:], sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        # Dataclasses resolve postponed annotations through the module registry.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    finally:
        sys.path[:] = old_path
        sys.dont_write_bytecode = old_bytecode
    return module


def _approval_gaps(project: Path) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for name in ("brands", "brand_candidates", "category_rules", "category_candidates"):
        path = project / f"config/registries/{name}.csv"
        if not path.exists():
            gaps.append({"registry": name, "reason": "missing"})
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            gaps.append({"registry": name, "reason": "empty"})
        for index, row in enumerate(rows, start=2):
            if ((name == "brands" and row.get("ownership_type") not in
                 {"owned", "competitor"}) or
                    (name != "brands" and row.get("review_status") != "approved")):
                gaps.append({"registry": name, "row": index,
                             "reason": "not_approved"})
    return gaps


def _audit(project: Path, raw_date: date | None, runner: Any) -> dict[str, Any]:
    rows = runner.audit_raw(project / "data/raw", raw_date)
    counts = Counter({key: 0 for key in ("success", "empty", "failure", "unsupported")})
    responses = []
    for row in rows:
        if row["role"] != "response":
            continue
        status, reason = "failure", None
        if row["triple_valid"]:
            try:
                path = project / "data/raw" / row["path"]
                metadata = json.loads(path.with_name("metadata.json").read_bytes())
                engine = str(metadata["platform_or_engine"]).casefold()
                supported = (runner.supported_serp_engines() | {"baidu"}
                             if row["category"] == "serp" else {"chat_gpt", "gemini"})
                if (
                    metadata["provider"].casefold() != "dataforseo"
                    or engine not in supported
                ):
                    status = "unsupported"
                else:
                    _, block = runner.envelope(json.loads(path.read_bytes()))
                    outcome, task, _ = runner.provider_status(block)
                    if row["category"] == "llm" and len(task.get("result") or []) > 1:
                        status = "unsupported"
                    elif outcome in {"pending", "provider_error"}:
                        reason = outcome
                    elif outcome == "no_results":
                        status = "empty"
                    else:
                        # Audit confirms a provider contract, not parser/query success.
                        results = task["result"]
                        if task.get("status_code") != 20000:
                            status = "unsupported"
                        elif all(
                            isinstance(result.get("items"), list) for result in results
                        ):
                            status = (
                                "success" if any(result["items"] for result in results)
                                else "empty"
                            )
                        else:
                            status = "unsupported"
            except (KeyError, TypeError, ValueError, OSError) as exc:
                status, reason = "unsupported", str(exc)
        counts[status] += 1
        responses.append({"path": row["path"], "status": status, "reason": reason})
    return {"files": rows, "response_coverage": dict(counts), "responses": responses,
            "file_count": len(rows), "response_count": len(responses),
            "quarantine_files": sum(not row["json_valid"] or not row["triple_valid"]
                                    for row in rows),
            "success_basis": (
                "verified provider response contract only; no query row inference"
            )}


def _new_run(output: Path) -> Path:
    folder = output / f"run_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def _base(project: Path, folder: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "run_id": folder.name,
            "project": str(project), "run_directory": str(folder),
            "manifest_path": str(folder / "run_manifest.json"),
            "started_at": datetime.now(UTC).isoformat(), "status": "failed",
            **snapshot, "steps": [], "outputs": {}, "tests": {"executed": False},
            "dbt_run": False, "publication": False, "api_calls": False,
            "registry_approval_gaps": _approval_gaps(project)}


def _finish(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    _atomic(Path(manifest["manifest_path"]), manifest)
    return manifest


def audit_project(
    project: Path, output: Path, raw_date: str | None = None,
) -> dict[str, Any]:
    """Read raw metadata/contracts only; write a new audit manifest under output."""
    project, output = _paths(project, output)
    selected_date = _date(raw_date)
    snapshot = _snapshot(project, selected_date)
    manifest = _base(project, _new_run(output), snapshot)
    try:
        manifest["audit"] = _audit(project, selected_date, _runner(project))
        manifest["steps"] = [{"stage": "audit", "status": "success"}]
        coverage = manifest["audit"]["response_coverage"]
        manifest["status"] = "partial" if (
            not manifest["audit"]["response_count"] or coverage["failure"]
            or coverage["unsupported"] or manifest["audit"]["quarantine_files"]
        ) else "success"
        manifest["source_unchanged"] = snapshot == _snapshot(project, selected_date)
        if not manifest["source_unchanged"]:
            raise RuntimeError("source inputs changed during audit")
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    return _finish(manifest)


def _compatible(previous: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if (previous.get("schema_version") != SCHEMA_VERSION or
            previous.get("status") not in {"success", "partial"} or
            previous.get("compatibility_hash") != snapshot["compatibility_hash"] or
            previous.get("source_unchanged") is not True):
        return False
    if any(previous.get(key) != snapshot[key] for key in (
        "scope", "input_hashes", "code_hashes", "registry_hashes", "provenance_hashes"
    )):
        return False
    steps = {step["stage"] for step in previous.get("steps", [])
             if step.get("status") in {"success", "reused"}}
    if not {"normalize", "evidence"}.issubset(steps):
        return False
    outputs = previous.get("output_hashes", {})
    database = previous.get("outputs", {}).get("database")
    return bool(database and database in outputs and outputs and all(
        Path(path).is_file() and _hash(Path(path)) == checksum
        for path, checksum in outputs.items()
    ))


def _copy_inputs(project: Path, work: Path, snapshot: dict[str, Any]) -> None:
    # No symlinks: the runner can only write within its new private project.
    for group in ("input_hashes", "registry_hashes", "provenance_hashes"):
        for relative, checksum in snapshot[group].items():
            source, destination = project / relative, work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if _hash(destination) != checksum:
                raise RuntimeError(f"input changed while copying: {relative}")


def run_pipeline(project: Path, output: Path, *, raw_date: str | None = None,
                 stages: tuple[str, ...] = ("normalize", "evidence"),
                 previous_manifest: Path | None = None) -> dict[str, Any]:
    """Build or copy a compatible completed upstream into a distinct new warehouse.

    Evidence-only requires a fully compatible prior normalize/evidence output.
    With normalize selected, any incompatibility safely rebuilds the coupled job.
    Failures return and persist a failed manifest; argument/path errors raise.
    """
    project, output = _paths(project, output)
    selected_date = _date(raw_date)
    if (
        not stages or len(set(stages)) != len(stages)
        or set(stages) - {s.name for s in STAGES}
    ):
        raise ValueError("stages must be unique normalize/evidence selections")
    snapshot = _snapshot(project, selected_date)
    folder = _new_run(output)
    manifest = _base(project, folder, snapshot)
    manifest["requested_stages"] = list(stages)
    manifest["execution_note"] = "legacy runner couples normalize and evidence"
    try:
        previous = None
        if previous_manifest is not None:
            try:
                previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
                if not isinstance(previous, dict):
                    previous = None
            except (OSError, ValueError):
                previous = None
        reuse = previous is not None and _compatible(previous, snapshot)
        if "normalize" not in stages and not reuse:
            raise ValueError("evidence-only requires compatible prior upstream output")
        runner = _runner(project)
        manifest["audit"] = _audit(project, selected_date, runner)
        if reuse:
            assert previous is not None
            destination = folder / "warehouse.duckdb"
            shutil.copyfile(previous["outputs"]["database"], destination)
            if (
                _hash(destination)
                != previous["output_hashes"][previous["outputs"]["database"]]
            ):
                raise RuntimeError("prior output changed while copying")
            manifest["outputs"] = {"database": str(destination)}
            manifest["runner_summary"] = previous.get("runner_summary", {})
            manifest["steps"] = [{"stage": name, "status": "reused"}
                                 for name in ("normalize", "evidence")]
            manifest["reused_manifest"] = str(previous_manifest)
        else:
            work = folder / "working_project"
            _copy_inputs(project, work, snapshot)
            manifest["steps"] = [{"stage": "normalize", "status": "running"}]
            old_bytecode = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                summary = runner.run(work, raw_date=selected_date)
            finally:
                sys.dont_write_bytecode = old_bytecode
            database = Path(summary["database"]).resolve()
            export = Path(summary["export"]).resolve()
            if not _inside(database, work) or not _inside(export, work):
                raise RuntimeError("runner returned outputs outside isolated project")
            if not database.is_file() or not (export / "summary.json").is_file():
                raise RuntimeError("runner outputs are missing")
            if (
                summary.get("raw_unchanged") is not True
                or summary.get("publication") is not False
            ):
                raise RuntimeError("runner safety verification failed")
            if "response_evidence_observations" not in summary:
                raise RuntimeError(
                    "runner did not confirm embedded evidence enrichment"
                )
            manifest["runner_summary"] = summary
            manifest["outputs"] = {"database": str(database), "export": str(export)}
            manifest["steps"] = [
                {"stage": "normalize", "status": "success",
                 "executor": "transform_all_raw.run"},
                {"stage": "evidence", "status": "success",
                 "executor": "embedded enrich_database/enrich_features"},
            ]
        manifest["source_unchanged"] = snapshot == _snapshot(project, selected_date)
        if not manifest["source_unchanged"]:
            raise RuntimeError("source inputs changed during run")
        artifacts = [Path(manifest["outputs"]["database"])]
        if "export" in manifest["outputs"]:
            artifacts += _files(Path(manifest["outputs"]["export"]))
        manifest["output_hashes"] = {str(path): _hash(path) for path in artifacts}
        summary = manifest["runner_summary"]
        manifest["quarantine_counts"] = {
            key: summary.get(key, 0) for key in (
                "quarantined_responses", "unsupported_responses",
                "parse_quarantine_events",
            )
        }
        manifest["registry_approval_gaps"] += (
            summary.get("registries", {}).get("excluded", [])
        )
        coverage = manifest["audit"]["response_coverage"]
        manifest["status"] = "partial" if (
            any(manifest["quarantine_counts"].values()) or coverage["failure"]
            or coverage["unsupported"] or not manifest["audit"]["response_count"]
        ) else "success"
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        manifest["source_unchanged"] = snapshot == _snapshot(project, selected_date)
        for step in manifest["steps"]:
            if step["status"] == "running":
                step["status"] = "failed"
    return _finish(manifest)


def review_opportunity(database_path: Path, opportunity_id: str, *, status: str,
                       owner: str, notes: str) -> dict[str, Any]:
    """Append a human analyst decision; never change presentation or approve a job."""
    import duckdb

    if status not in REVIEW_STATES:
        raise ValueError("invalid review status")
    if not opportunity_id.strip() or not owner.strip() or not isinstance(notes, str):
        raise ValueError("opportunity_id and owner are required; notes must be text")
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise ValueError("database must already exist")
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            columns = {row[0] for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='presentation' AND table_name='platform_documents'"
            ).fetchall()}
            payload = next((
                name for name in ("payload_json", "document_json", "content_json")
                if name in columns
            ), None)
            if "kind" not in columns or payload is None:
                raise ValueError(
                    "completed opportunity document contract is unavailable"
                )
            if "release_id" in columns:
                release_metadata = connection.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='presentation' "
                    "AND table_name='platform_releases'"
                ).fetchone()
                assert release_metadata is not None
                release_table = (
                    "platform_releases" if release_metadata[0] else "releases"
                )
                sql = (f'SELECT d."{payload}" FROM presentation.platform_documents d '
                       f"JOIN presentation.{release_table} r "
                       "ON r.release_id=d.release_id "
                       "WHERE d.kind=? AND r.status=?")
            elif "status" in columns:
                sql = (f'SELECT "{payload}" FROM presentation.platform_documents '
                       "WHERE kind=? AND status=?")
            else:
                raise ValueError("document completion cannot be verified")
            documents = connection.execute(
                sql, ["opportunities", "completed"]
            ).fetchall()

            def known(value: Any) -> bool:
                if isinstance(value, list):
                    return any(known(item) for item in value)
                if isinstance(value, dict):
                    if value.get("opportunity_id") == opportunity_id:
                        return True
                    return any(
                        known(value[key]) for key in ("opportunities", "rows", "items")
                        if key in value
                    )
                return False

            if not any(known(json.loads(row[0])) for row in documents):
                raise ValueError(
                    "unknown opportunity in completed presentation documents"
                )
            connection.execute("CREATE SCHEMA IF NOT EXISTS governance")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS governance.platform_opportunity_reviews ("
                "review_id VARCHAR PRIMARY KEY, opportunity_id VARCHAR NOT NULL, "
                "status VARCHAR NOT NULL CHECK (status IN "
                "('draft','under_review','approved','rejected',"
                "'snoozed','completed')), "
                "owner VARCHAR NOT NULL, notes VARCHAR NOT NULL, "
                "reviewed_at TIMESTAMPTZ NOT NULL)"
            )
            result = {"review_id": str(uuid4()), "opportunity_id": opportunity_id,
                      "status": status, "owner": owner, "notes": notes,
                      "reviewed_at": datetime.now(UTC).isoformat()}
            connection.execute(
                "INSERT INTO governance.platform_opportunity_reviews "
                "VALUES (?, ?, ?, ?, ?, ?)",
                list(result.values()),
            )
            connection.execute("COMMIT")
            return result
        except Exception:
            connection.execute("ROLLBACK")
            raise