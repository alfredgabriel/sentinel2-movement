"""Tests for CLI arguments and configuration loading."""

from pathlib import Path

import pytest

from s2motion.cli import build_parser, load_toml_config


def test_cli_parser_crops() -> None:
    """Verify crops subcommand arguments parsing."""
    parser = build_parser()
    args = parser.parse_args(["crops", "--start", "2026-01-01", "--end", "2026-06-01", "--max-cloud", "5.0"])
    assert args.subcommand == "crops"
    assert args.start == "2026-01-01"
    assert args.end == "2026-06-01"
    assert args.max_cloud == 5.0


def test_cli_parser_view() -> None:
    """Verify view subcommand arguments parsing."""
    parser = build_parser()
    args = parser.parse_args(["view", "--config", "examples/loiu_2026-08-12.toml"])
    assert args.subcommand == "view"
    assert args.config == "examples/loiu_2026-08-12.toml"


def test_cli_parser_measure() -> None:
    """Verify measure subcommand arguments parsing."""
    parser = build_parser()
    args = parser.parse_args([
        "measure",
        "--config", "examples/loiu_2026-08-12.toml",
        "--runway-heading", "120.0",
        "--out", "docs/img/output.png",
    ])
    assert args.subcommand == "measure"
    assert args.config == "examples/loiu_2026-08-12.toml"
    assert args.runway_heading == 120.0
    assert args.out == "docs/img/output.png"


def test_load_toml_config_valid() -> None:
    """Verify loading the actual example configuration file."""
    cfg = load_toml_config(Path("examples/loiu_2026-08-12.toml"))
    assert cfg["scene"]["date"] == "2026-08-12"
    assert cfg["seeds"]["red"] == [66, 158]
    assert cfg["seeds"]["green"] == [70, 160]
    assert cfg["seeds"]["blue"] == [74, 162]


def test_load_toml_config_not_found() -> None:
    """Verify error on non-existent config file."""
    with pytest.raises(FileNotFoundError):
        load_toml_config(Path("non_existent_config.toml"))
