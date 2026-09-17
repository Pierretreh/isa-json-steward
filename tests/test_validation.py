"""
Unit tests for validation utilities.
"""

import pytest

from utils.validation import (
    is_safe_id,
    validate_email,
    validate_filename,
    validate_id,
    validate_path,
    validate_required_fields,
    validate_url,
)


@pytest.mark.unit
class TestValidateId:
    """Tests for validate_id function."""

    def test_valid_id(self):
        """Test that valid IDs pass validation."""
        assert validate_id("test_id") == (True, None)
        assert validate_id("test-123") == (True, None)
        assert validate_id("test_id_123") == (True, None)

    def test_empty_id(self):
        """Test that empty IDs fail validation."""
        result = validate_id("")
        assert result == (False, "ID cannot be empty")

    def test_non_string_id(self):
        """Test that non-string IDs fail validation."""
        result = validate_id(123)
        assert result == (False, "ID must be a string")

    def test_too_long_id(self):
        """Test that IDs longer than 100 characters fail validation."""
        long_id = "a" * 101
        result = validate_id(long_id)
        assert result == (False, "ID too long (max 100 characters)")

    def test_invalid_characters_id(self):
        """Test that IDs with invalid characters fail validation."""
        result = validate_id("test id with spaces")
        assert result == (
            False,
            "ID can only contain alphanumeric characters, underscores, and hyphens",
        )


@pytest.mark.unit
class TestValidateFilename:
    """Tests for validate_filename function."""

    def test_valid_filename(self):
        """Test that valid filenames pass validation."""
        assert validate_filename("test.txt") == (True, None)
        assert validate_filename("document.pdf") == (True, None)
        assert validate_filename("image_123.jpg") == (True, None)

    def test_empty_filename(self):
        """Test that empty filenames fail validation."""
        result = validate_filename("")
        assert result == (False, "Filename cannot be empty")

    def test_invalid_characters_filename(self):
        """Test that filenames with invalid characters fail validation."""
        invalid_chars = '<>:"/\\|?*'
        result = validate_filename(f"test{invalid_chars}file.txt")
        assert result[0] is False
        assert "invalid characters" in result[1].lower()

    def test_reserved_windows_filename(self):
        """Test that reserved Windows filenames fail validation."""
        reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
        for name in reserved_names:
            result = validate_filename(f"{name}.txt")
            assert result[0] is False
            assert "reserved" in result[1].lower()


@pytest.mark.security
@pytest.mark.unit
class TestIsSafeId:
    """Tests for is_safe_id function."""

    def test_safe_id(self):
        """Test that safe IDs return True."""
        assert is_safe_id("test_id") is True
        assert is_safe_id("test-123") is True
        assert is_safe_id("id_123") is True

    def test_empty_id(self):
        """Test that empty IDs return False."""
        assert is_safe_id("") is False

    def test_path_traversal_id(self):
        """Test that IDs with path traversal return False."""
        assert is_safe_id("../test") is False
        assert is_safe_id("test/../../etc") is False
        assert is_safe_id("test\\windows\\path") is False

    def test_slash_in_id(self):
        """Test that IDs with slashes return False."""
        assert is_safe_id("test/id") is False
        assert is_safe_id("test\\id") is False

    def test_too_long_id(self):
        """Test that IDs longer than 100 characters return False."""
        long_id = "a" * 101
        assert is_safe_id(long_id) is False


@pytest.mark.security
@pytest.mark.unit
@pytest.mark.security
@pytest.mark.unit
class TestValidatePath:
    """Tests for validate_path function."""

    def test_valid_path(self, temp_dir):
        """Test that valid paths pass validation."""
        # Create the file first so it exists
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")
        result = validate_path(temp_dir, str(test_file))
        assert result[0] is True
        assert result[1] == test_file.resolve()

    def test_path_traversal(self, temp_dir):
        """Test that path traversal attempts fail validation."""
        result = validate_path(temp_dir, "../etc/passwd")
        assert result[0] is False
        assert result[1] is None

    def test_absolute_path(self, temp_dir):
        """Test that absolute paths outside base are rejected."""
        result = validate_path(temp_dir, "/etc/passwd")
        assert result[0] is False
        assert result[1] is None


@pytest.mark.unit
class TestValidateRequiredFields:
    """Tests for validate_required_fields function."""

    def test_all_required_fields_present(self):
        """Test that validation passes when all required fields are present."""
        data = {"name": "Test", "description": "Test description", "value": 42}
        required_fields = ["name", "description", "value"]

        is_valid, missing = validate_required_fields(data, required_fields)

        assert is_valid is True
        assert len(missing) == 0

    def test_missing_required_fields(self):
        """Test that validation fails when required fields are missing."""
        data = {"name": "Test"}
        required_fields = ["name", "description", "value"]

        is_valid, missing = validate_required_fields(data, required_fields)

        assert is_valid is False
        assert "description" in missing
        assert "value" in missing
        assert len(missing) == 2

    def test_empty_required_fields(self):
        """Test that validation fails when required fields are empty."""
        data = {"name": "", "description": None, "value": 0}
        required_fields = ["name", "description", "value"]

        is_valid, missing = validate_required_fields(data, required_fields)

        assert is_valid is False
        assert "name" in missing
        assert "description" in missing
        assert "value" in missing

    def test_empty_required_fields_list(self):
        """Test that validation passes when no fields are required."""
        data = {"name": "Test"}
        required_fields = []

        is_valid, missing = validate_required_fields(data, required_fields)

        assert is_valid is True
        assert len(missing) == 0


@pytest.mark.unit
class TestValidateEmail:
    """Tests for validate_email function."""

    def test_valid_email(self):
        """Test that valid email addresses pass validation."""
        assert validate_email("user@example.com") == (True, None)
        assert validate_email("user.name@example.com") == (True, None)
        assert validate_email("user+tag@example.com") == (True, None)
        assert validate_email("user@sub.example.com") == (True, None)

    def test_empty_email(self):
        """Test that empty email fails validation."""
        result = validate_email("")
        assert result == (False, "Email cannot be empty")

    def test_invalid_email_format(self):
        """Test that invalid email formats fail validation."""
        invalid_emails = [
            "user",
            "user@",
            "@example.com",
            "user@example",
            "user..name@example.com",
            "user@.example.com",
            "user name@example.com",
            "user@exa mple.com",
        ]

        for email in invalid_emails:
            result = validate_email(email)
            assert result[0] is False
            assert result[1] is not None


@pytest.mark.unit
class TestValidateUrl:
    """Tests for validate_url function."""

    def test_valid_http_url(self):
        """Test that valid HTTP URLs pass validation."""
        assert validate_url("http://example.com") == (True, None)
        assert validate_url("http://example.com/path") == (True, None)
        assert validate_url("http://example.com:8080") == (True, None)

    def test_valid_https_url(self):
        """Test that valid HTTPS URLs pass validation."""
        assert validate_url("https://example.com") == (True, None)
        assert validate_url("https://example.com/path") == (True, None)
        assert validate_url("https://example.com:443/path") == (True, None)

    def test_valid_localhost_url(self):
        """Test that localhost URLs pass validation."""
        assert validate_url("http://localhost") == (True, None)
        assert validate_url("http://localhost:8080") == (True, None)

    def test_empty_url(self):
        """Test that empty URL fails validation."""
        result = validate_url("")
        assert result == (False, "URL cannot be empty")

    def test_invalid_url_format(self):
        """Test that invalid URL formats fail validation."""
        invalid_urls = ["example.com", "ftp://example.com", "http://", "not a url"]

        for url in invalid_urls:
            result = validate_url(url)
            assert result[0] is False
            assert result[1] is not None
