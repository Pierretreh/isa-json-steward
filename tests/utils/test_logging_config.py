"""
Unit tests for utils.logging_config.

These tests cover setup_logging() handler configuration, log levels,
log file creation, and get_logger() behavior.
"""

import logging
import sys
from typing import List

import pytest

from utils.logging_config import get_logger, setup_logging


def _root() -> logging.Logger:
    """Return the root logger."""
    return logging.getLogger()


def _stream_handlers(root: logging.Logger) -> List[logging.Handler]:
    """Stream handlers that are not file handlers (FileHandler subclasses StreamHandler)."""
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]


def _file_handlers(root: logging.Logger) -> List[logging.FileHandler]:
    """All file handlers attached to the root logger."""
    return [h for h in root.handlers if isinstance(h, logging.FileHandler)]


@pytest.mark.unit
class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_logger_instance(self):
        """get_logger() returns a logging.Logger instance."""
        logger = get_logger("test.logger")

        assert isinstance(logger, logging.Logger)

    def test_logger_has_requested_name(self):
        """The returned logger has the name passed to get_logger()."""
        logger = get_logger("utils.logging_config.test")

        assert logger.name == "utils.logging_config.test"

    def test_returns_same_instance_as_standard_getlogger(self):
        """get_logger() uses the standard logger registry (same instance)."""
        name = "utils.logging_config.registry_test"
        assert get_logger(name) is logging.getLogger(name)

    def test_hierarchical_logger_names(self):
        """Dotted hierarchical logger names are supported."""
        logger = get_logger("package.module.submodule")

        assert logger.name == "package.module.submodule"

    def test_missing_name_raises_type_error(self):
        """Calling get_logger() without a name raises TypeError."""
        with pytest.raises(TypeError):
            get_logger()  # type: ignore[call-arg]


@pytest.mark.unit
class TestSetupLoggingBasic:
    """Tests for setup_logging() default behavior."""

    def test_returns_none(self):
        """setup_logging() is a void configuration function."""
        assert setup_logging() is None

    def test_configures_root_logger_level(self):
        """Default setup configures the root logger at INFO level."""
        setup_logging()

        assert _root().level == logging.INFO

    def test_attaches_stream_handler(self):
        """A stream handler is attached to the root logger."""
        setup_logging()

        assert len(_stream_handlers(_root())) == 1

    def test_stream_handler_writes_to_stdout(self):
        """The default stream handler writes to sys.stdout."""
        setup_logging()

        handlers = _stream_handlers(_root())
        assert handlers[0].stream is sys.stdout

    def test_no_file_handler_without_log_file(self):
        """Without a log file, only the stream handler is attached."""
        setup_logging()

        assert _file_handlers(_root()) == []

    def test_default_format_applied(self):
        """The default log format contains the expected fields."""
        setup_logging()

        formatter = _stream_handlers(_root())[0].formatter
        assert formatter is not None
        fmt = formatter._fmt  # noqa: SLF001 - inspecting logging internals
        assert "%(asctime)s" in fmt
        assert "%(name)s" in fmt
        assert "%(levelname)s" in fmt
        assert "%(message)s" in fmt

    def test_force_resets_existing_handlers(self):
        """Calling setup_logging() again does not accumulate handlers (force=True)."""
        root = _root()
        root.addHandler(logging.NullHandler())

        setup_logging()
        first_count = len(root.handlers)

        setup_logging()
        second_count = len(root.handlers)

        assert second_count == first_count
        assert len(_stream_handlers(root)) == 1
        assert len(_file_handlers(root)) == 0


@pytest.mark.unit
class TestSetupLoggingLevels:
    """Tests for setup_logging() with different log levels."""

    @pytest.mark.parametrize(
        "level_name,expected_level",
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ],
    )
    def test_log_levels(self, level_name, expected_level):
        """Each named level is applied to the root logger."""
        setup_logging(log_level=level_name)

        assert _root().level == expected_level

    def test_lowercase_level_name_is_normalized(self):
        """Lowercase level names are upper-cased before lookup."""
        setup_logging(log_level="debug")

        assert _root().level == logging.DEBUG

    def test_unknown_level_falls_back_to_info(self):
        """An unrecognized level name falls back to INFO via getattr default."""
        setup_logging(log_level="NOT_A_LEVEL")

        assert _root().level == logging.INFO


@pytest.mark.unit
class TestSetupLoggingFile:
    """Tests for setup_logging() with a log file."""

    def test_creates_log_file(self, tmp_path):
        """Providing a log file path creates the file."""
        log_file = tmp_path / "app.log"

        setup_logging(log_file=log_file)

        assert log_file.exists()
        assert log_file.is_file()

    def test_attaches_file_handler(self, tmp_path):
        """Providing a log file path attaches a FileHandler."""
        log_file = tmp_path / "app.log"

        setup_logging(log_file=log_file)

        file_handlers = _file_handlers(_root())
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == str(log_file)

    def test_stream_handler_still_present(self, tmp_path):
        """A file handler is added in addition to the stream handler."""
        setup_logging(log_file=tmp_path / "app.log")

        assert len(_stream_handlers(_root())) == 1
        assert len(_file_handlers(_root())) == 1

    def test_creates_missing_parent_directories(self, tmp_path):
        """Parent directories of the log file are created as needed."""
        log_file = tmp_path / "nested" / "deeper" / "dir" / "app.log"
        assert not log_file.parent.exists()

        setup_logging(log_file=log_file)

        assert log_file.parent.exists()
        assert log_file.exists()

    def test_log_messages_are_written_to_file(self, tmp_path):
        """Log records emitted after setup are persisted to the log file."""
        log_file = tmp_path / "app.log"
        setup_logging(log_file=log_file, log_level="DEBUG")

        logger = get_logger("test.file_logging")
        logger.info("hello file handler")
        for handler in _root().handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "hello file handler" in content
        assert "INFO" in content
        assert "test.file_logging" in content

    def test_file_handler_uses_utf8_encoding(self, tmp_path):
        """The file handler is configured with utf-8 encoding."""
        log_file = tmp_path / "app.log"

        setup_logging(log_file=log_file)

        file_handler = _file_handlers(_root())[0]
        assert file_handler.encoding == "utf-8"


@pytest.mark.unit
class TestSetupLoggingFormat:
    """Tests for setup_logging() with a custom format."""

    def test_custom_format_applied_to_stream_handler(self, tmp_path):
        """A custom format string is used by the stream handler."""
        setup_logging(log_format="CUSTOM|%(levelname)s|%(message)s")

        formatter = _stream_handlers(_root())[0].formatter
        assert formatter is not None
        assert formatter._fmt == "CUSTOM|%(levelname)s|%(message)s"  # noqa: SLF001

    def test_custom_format_applied_to_file_handler(self, tmp_path):
        """A custom format string is used by the file handler."""
        setup_logging(log_file=tmp_path / "app.log", log_format="|%(message)s|")

        formatter = _file_handlers(_root())[0].formatter
        assert formatter is not None
        assert formatter._fmt == "|%(message)s|"  # noqa: SLF001

    def test_custom_format_does_not_leak_between_calls(self, tmp_path):
        """A subsequent default setup replaces the custom format (force=True)."""
        setup_logging(log_format="CUSTOM|%(message)s")
        setup_logging()

        formatter = _stream_handlers(_root())[0].formatter
        assert formatter is not None
        assert "CUSTOM" not in formatter._fmt  # noqa: SLF001
