"""Unit tests for configuration loader functionality.

This module tests the ConfigurationLoader class, file loading, validation,
and configuration management functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.config.exceptions import (
    ConfigurationError,
    ConfigurationFileError,
    ConfigurationValidationError,
)
from src.config.loader import (
    ConfigurationLoader,
    get_config,
    is_config_loaded,
    load_config,
    reload_config,
)
from src.config.models import Config


class TestConfigurationLoader:
    """Tests for ConfigurationLoader class methods."""

    def test_configuration_loader_initialization(self):
        """
        Why: Ensure ConfigurationLoader initializes with proper default state
        What: Tests that new loader has no config loaded and correct initial state
        How: Creates new loader and verifies initial property values
        """
        loader = ConfigurationLoader()

        assert loader.config is None
        assert loader.config_file_path is None
        assert loader.is_loaded is False
        assert loader._loaded_from_sources["file"] is False
        assert loader._loaded_from_sources["env"] is False
        assert loader._loaded_from_sources["defaults"] is True

    def test_load_from_dict_with_valid_data(self):
        """
        Why: Enable configuration loading from dictionary for testing and
             programmatic setup
        What: Tests that valid configuration dictionary creates proper Config instance
        How: Provides valid config dict and verifies Config object creation and state
        """
        loader = ConfigurationLoader()
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        config = loader.load_from_dict(config_data)

        assert isinstance(config, Config)
        assert loader.is_loaded is True
        assert loader.config is config
        assert loader._loaded_from_sources["dict"] is True

    def test_load_from_dict_with_invalid_data(self):
        """
        Why: Ensure proper error handling when configuration dictionary is malformed
        What: Tests that invalid config data raises ConfigurationValidationError
        How: Provides invalid config dict and verifies appropriate exception is raised
        """
        loader = ConfigurationLoader()
        invalid_config_data = {
            "database": {"url": "invalid://url"},  # Invalid URL scheme
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {},  # Empty LLM config
            "repositories": [],  # Empty repositories
        }

        with pytest.raises(ConfigurationValidationError):
            loader.load_from_dict(invalid_config_data)

    def test_load_from_file_with_valid_yaml(self):
        """
        Why: Enable configuration loading from YAML files for production deployment
        What: Tests that valid YAML configuration file is loaded correctly
        How: Creates temporary YAML file with valid config and loads it
        """
        loader = ConfigurationLoader()
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = loader.load_from_file(temp_path)

            assert isinstance(config, Config)
            assert loader.is_loaded is True
            assert loader.config_file_path == temp_path.resolve()
            assert loader._loaded_from_sources["file"] is True
        finally:
            temp_path.unlink()

    def test_load_from_file_nonexistent_file(self):
        """
        Why: Provide clear error messages when configuration files are missing
        What: Tests that attempting to load non-existent file raises
              ConfigurationFileError
        How: Attempts to load from non-existent path and verifies error message
        """
        loader = ConfigurationLoader()
        nonexistent_path = Path("/nonexistent/config.yaml")

        with pytest.raises(
            ConfigurationFileError, match="Configuration file not found"
        ):
            loader.load_from_file(nonexistent_path)

    def test_load_from_file_directory_instead_of_file(self):
        """
        Why: Prevent confusion when user provides directory path instead of file path
        What: Tests that providing directory path raises appropriate error
        How: Creates temporary directory and attempts to load it as config file
        """
        loader = ConfigurationLoader()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with pytest.raises(
                ConfigurationFileError, match="Configuration path is not a file"
            ):
                loader.load_from_file(temp_path)

    def test_load_from_file_invalid_yaml(self):
        """
        Why: Provide clear error messages when YAML files are malformed
        What: Tests that invalid YAML syntax raises ConfigurationFileError
              with YAML details
        How: Creates file with invalid YAML and attempts to load it
        """
        loader = ConfigurationLoader()
        invalid_yaml = "invalid: yaml: content: ["  # Unclosed bracket

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_yaml)
            temp_path = Path(f.name)

        try:
            with pytest.raises(
                ConfigurationFileError, match="Failed to parse YAML configuration"
            ):
                loader.load_from_file(temp_path)
        finally:
            temp_path.unlink()

    def test_load_from_file_empty_file(self):
        """
        Why: Handle edge case of completely empty configuration files gracefully
        What: Tests that empty YAML file creates config with defaults
        How: Creates empty file and verifies it loads with default configuration
        """
        loader = ConfigurationLoader()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = Path(f.name)

        try:
            # This should fail because required fields are missing
            with pytest.raises(ConfigurationValidationError):
                loader.load_from_file(temp_path)
        finally:
            temp_path.unlink()

    def test_load_default_configuration(self):
        """
        Why: Provide fallback configuration for development and testing environments
        What: Tests that load_default() creates minimal working configuration
        How: Calls load_default and verifies it creates valid Config with test values
        """
        loader = ConfigurationLoader()
        config = loader.load_default()

        assert isinstance(config, Config)
        assert loader.is_loaded is True
        assert config.database.url == "sqlite:///./test.db"
        assert len(config.repositories) == 1
        assert config.repositories[0].url == "https://github.com/example/repo"

    def test_find_config_file_current_directory(self):
        """
        Why: Support standard configuration file discovery for ease of deployment
        What: Tests that find_config_file locates config.yaml in current directory
        How: Creates config.yaml in temporary directory and searches for it
        """
        loader = ConfigurationLoader()

        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text("test: config")

            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                found_path = loader.find_config_file("config.yaml")

                assert found_path == config_file

    def test_find_config_file_environment_variable(self):
        """
        Why: Allow override of configuration file location via environment variable
        What: Tests that AGENTIC_CONFIG_PATH environment variable is respected
        How: Sets environment variable and verifies file is found at that location
        """
        loader = ConfigurationLoader()

        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "custom-config.yaml"
            config_file.write_text("test: config")

            with patch.dict("os.environ", {"AGENTIC_CONFIG_PATH": str(config_file)}):
                found_path = loader.find_config_file()

                assert found_path == config_file

    def test_find_config_file_not_found(self):
        """
        Why: Handle gracefully when no configuration file exists in standard locations
        What: Tests that find_config_file returns None when no file is found
        How: Searches for non-existent file and verifies None is returned
        """
        loader = ConfigurationLoader()

        with (
            patch("pathlib.Path.cwd", return_value=Path("/nonexistent")),
            patch.dict("os.environ", {}, clear=True),
        ):
            found_path = loader.find_config_file("nonexistent.yaml")

            assert found_path is None

    def test_auto_load_success(self):
        """
        Why: Provide convenient automatic configuration loading for typical deployments
        What: Tests that auto_load successfully finds and loads configuration file
        How: Creates config file and verifies auto_load finds and loads it
        """
        loader = ConfigurationLoader()
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                config = loader.auto_load()

                assert isinstance(config, Config)
                assert loader.is_loaded is True

    def test_auto_load_no_file_found(self):
        """
        Why: Provide clear error when no configuration file can be found automatically
        What: Tests that auto_load raises ConfigurationFileError when no file exists
        How: Attempts auto_load with no config files present and verifies error
        """
        loader = ConfigurationLoader()

        with (
            patch("pathlib.Path.cwd", return_value=Path("/nonexistent")),
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(
                ConfigurationFileError,
                match="No configuration file.*found in standard locations",
            ),
        ):
            loader.auto_load()

    def test_get_loading_info(self):
        """
        Why: Provide debugging information about configuration loading for
             troubleshooting
        What: Tests that get_loading_info returns comprehensive loading metadata
        How: Loads config and verifies loading info contains expected metadata
        """
        loader = ConfigurationLoader()
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        loader.load_from_dict(config_data)
        loading_info = loader.get_loading_info()

        assert loading_info["loaded"] is True
        assert loading_info["config_file"] is None  # Dict loading
        assert loading_info["sources"]["dict"] is True
        assert loading_info["config_summary"] is not None
        assert "system" in loading_info["config_summary"]


class TestGlobalConfigurationFunctions:
    """Tests for global configuration management functions."""

    def test_load_config_with_explicit_path(self):
        """
        Why: Support explicit configuration file paths for custom deployments
        What: Tests that load_config accepts file paths and loads configuration
        How: Creates config file and loads it via explicit path
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            config = load_config(temp_path)
            assert isinstance(config, Config)
        finally:
            temp_path.unlink()

    def test_load_config_auto_discover(self):
        """
        Why: Enable zero-configuration loading for standard deployments
        What: Tests that load_config with auto_discover=True finds config files
        How: Creates config file in current directory and uses auto-discovery
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.yaml"
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                config = load_config(auto_discover=True)
                assert isinstance(config, Config)

    def test_load_config_default_fallback(self):
        """
        Why: Provide fallback when no configuration file is available
        What: Tests that load_config with auto_discover=False uses defaults
        How: Calls load_config without auto-discovery and verifies default config
        """
        config = load_config(auto_discover=False)
        assert isinstance(config, Config)
        assert config.database.url == "sqlite:///./test.db"

    def test_load_config_error_handling(self):
        """
        Why: Ensure configuration errors are properly wrapped and reported
        What: Tests that configuration errors are wrapped in ConfigurationError
        How: Attempts to load invalid config and verifies error type
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: [")  # Invalid YAML
            temp_path = Path(f.name)

        try:
            with pytest.raises(
                ConfigurationError, match="Failed to load configuration"
            ):
                load_config(temp_path)
        finally:
            temp_path.unlink()

    def test_get_config_when_loaded(self):
        """
        Why: Provide access to global configuration instance after loading
        What: Tests that get_config returns the loaded configuration
        How: Loads config and verifies get_config returns same instance
        """
        # First load a configuration
        config = load_config(auto_discover=False)

        # Then verify get_config returns it
        retrieved_config = get_config()
        assert retrieved_config is config

    def test_get_config_when_not_loaded(self):
        """
        Why: Provide clear error when attempting to access unloaded configuration
        What: Tests that get_config raises ConfigurationError when no config loaded
        How: Resets global state and verifies get_config raises appropriate error
        """
        # Reset global loader state
        from src.config.loader import _loader

        _loader._config = None

        with pytest.raises(ConfigurationError, match="No configuration loaded"):
            get_config()

    def test_is_config_loaded_true(self):
        """
        Why: Allow applications to check if configuration is available before using it
        What: Tests that is_config_loaded returns True when config is loaded
        How: Loads configuration and verifies is_config_loaded returns True
        """
        load_config(auto_discover=False)
        assert is_config_loaded() is True

    def test_is_config_loaded_false(self):
        """
        Why: Allow applications to detect when configuration needs to be loaded
        What: Tests that is_config_loaded returns False when no config is loaded
        How: Resets global state and verifies is_config_loaded returns False
        """
        # Reset global loader state
        from src.config.loader import _loader

        _loader._config = None

        assert is_config_loaded() is False

    def test_reload_config_from_file(self):
        """
        Why: Support configuration reloading for hot updates in production
        What: Tests that reload_config reloads from the same file path
        How: Loads config from file, modifies file, reloads, and verifies changes
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            # Initial load
            config1 = load_config(temp_path)

            # Modify file
            config_data["database"]["url"] = "sqlite:///modified.db"
            with open(temp_path, "w") as f:
                yaml.dump(config_data, f)

            # Reload
            config2 = reload_config()

            assert config2.database.url == "sqlite:///modified.db"
            assert config1.database.url != config2.database.url
        finally:
            temp_path.unlink()

    def test_reload_config_not_previously_loaded(self):
        """
        Why: Provide clear error when attempting to reload without initial load
        What: Tests that reload_config raises error when no config was previously loaded
        How: Resets global state and attempts reload without prior loading
        """
        # Reset global loader state
        from src.config.loader import _loader

        _loader._config = None
        _loader._config_file_path = None

        with pytest.raises(
            ConfigurationError,
            match="Cannot reload: no configuration was previously loaded",
        ):
            reload_config()


class TestConfigurationValidation:
    """Tests for configuration validation during loading."""

    def test_validation_can_be_disabled(self):
        """
        Why: Allow loading of partially invalid configurations for debugging
        What: Tests that validation=False parameter skips validation checks
        How: Loads invalid config with validation disabled and verifies it loads
        """
        loader = ConfigurationLoader()
        # This would normally fail higher-level validation
        # (enabled notifications without channels)
        invalid_config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {
                "enabled": True,
                "channels": [],
            },  # Invalid: enabled but no channels
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }

        # Should fail with validation enabled (default)
        with pytest.raises(ConfigurationValidationError):
            loader.load_from_dict(invalid_config_data, validate=True)

        # Should succeed with validation disabled
        config = loader.load_from_dict(invalid_config_data, validate=False)
        assert isinstance(config, Config)

    def test_validation_catches_cross_field_errors(self):
        """
        Why: Ensure configuration consistency is validated across related fields
        What: Tests that validation catches inconsistencies between related fields
        How: Creates config with mismatched default LLM provider and verifies error
        """
        loader = ConfigurationLoader()
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "default_llm_provider": "openai",  # Not in llm config
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with pytest.raises(ConfigurationValidationError):
            loader.load_from_dict(config_data)
