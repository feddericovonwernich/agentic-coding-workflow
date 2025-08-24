"""
Unit tests for ErrorSimulator class.

This module provides comprehensive tests for the ErrorSimulator implementation,
covering error generation, rate configuration, and metrics collection.
"""

import random
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.integration.fixtures.github_mock_server import ErrorSimulator


class TestErrorSimulator:
    """Test suite for ErrorSimulator class."""

    def test_error_rate_configuration(self) -> None:
        """
        Why: Ensure error rates are properly configured and bounded to valid ranges
             to prevent invalid configurations that could break testing scenarios.

        What: Tests that configure_error_simulation() properly sets error_rate
              within [0.0, 1.0] bounds and stores error codes correctly.

        How: Configures error simulator with various rates including edge cases,
             verifies rates are clamped to valid range and codes are stored.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Act & Assert - Normal configuration
        simulator.configure_error_simulation(0.3, [500, 502, 503])
        assert simulator.error_rate == 0.3
        assert simulator.error_codes == [500, 502, 503]

        # Act & Assert - Rate above 1.0 is clamped
        simulator.configure_error_simulation(1.5, [500])
        assert simulator.error_rate == 1.0
        assert simulator.error_codes == [500]

        # Act & Assert - Rate below 0.0 is clamped
        simulator.configure_error_simulation(-0.5, [503])
        assert simulator.error_rate == 0.0
        assert simulator.error_codes == [503]

        # Act & Assert - Edge cases
        simulator.configure_error_simulation(0.0, [429])
        assert simulator.error_rate == 0.0
        assert simulator.error_codes == [429]

        simulator.configure_error_simulation(1.0, [500, 502])
        assert simulator.error_rate == 1.0
        assert simulator.error_codes == [500, 502]

    def test_should_simulate_error_logic(self) -> None:
        """
        Why: Verify error decision logic correctly applies configured error rates
             to ensure predictable test behavior for error handling scenarios.

        What: Tests that should_simulate_error() returns tuple of (should_error, status_code)
              based on configured rate and increments request counter correctly.

        How: Uses fixed random seed for deterministic testing, configures
             error rate, and verifies error generation matches expectations.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(0.5, [500, 502])

        path = "/repos/owner/repo/pulls"

        # Use fixed seed for deterministic random behavior
        random.seed(42)

        # Act - Generate multiple error decisions
        results = []
        for _ in range(10):
            should_error, status_code = simulator.should_simulate_error(path)
            results.append(should_error)

        # Assert - With 0.5 rate, roughly half should be errors
        error_count = sum(results)
        assert 3 <= error_count <= 7  # Allow some variance
        assert simulator.request_count == 10

    def test_generate_500_error_response(self) -> None:
        """
        Why: Ensure 500 Internal Server Error responses are correctly formatted
             to match GitHub API error format for realistic testing.

        What: Tests that generate_error_response(500) returns proper structure
              with status code, headers, and error message matching GitHub format.

        How: Creates error response for status 500, verifies response contains
             correct status code, headers, and standard error message format.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Act
        error_response = simulator.generate_error_response(500)

        # Assert
        assert error_response is not None
        assert error_response["status_code"] == 500
        assert "headers" in error_response
        assert "response_data" in error_response
        assert error_response["response_data"]["message"] == "Internal Server Error"
        assert "documentation_url" in error_response["response_data"]

    def test_generate_502_error_response(self) -> None:
        """
        Why: Ensure 502 Bad Gateway errors are properly formatted for testing
             gateway and proxy failure scenarios in GitHub API interactions.

        What: Tests that generate_error_response(502) returns correct structure
              with appropriate error message for Bad Gateway errors.

        How: Creates error response for status 502, validates response format
             and verifies error message contains Bad Gateway text.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Act
        error_response = simulator.generate_error_response(502)

        # Assert
        assert error_response is not None
        assert error_response["status_code"] == 502
        assert "headers" in error_response
        assert "response_data" in error_response
        assert "Bad Gateway" in error_response["response_data"]["message"]
        assert "Retry-After" in error_response["headers"]

    def test_generate_503_error_response(self) -> None:
        """
        Why: Ensure 503 Service Unavailable errors are correctly generated
             for testing service downtime and maintenance scenarios.

        What: Tests that generate_error_response(503) returns proper error
              structure with Service Unavailable message and retry headers.

        How: Creates error response for status 503, verifies response includes
             correct status code, retry headers, and service unavailable message.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Act
        error_response = simulator.generate_error_response(503)

        # Assert
        assert error_response is not None
        assert error_response["status_code"] == 503
        assert "headers" in error_response
        assert "response_data" in error_response
        assert "Service Unavailable" in error_response["response_data"]["message"]
        assert "Retry-After" in error_response["headers"]
        assert error_response["headers"]["Retry-After"] == "30"

    def test_rate_limit_simulation(self) -> None:
        """
        Why: Verify rate limit errors (429) are properly formatted with GitHub's
             specific rate limit error structure for accurate rate limit testing.

        What: Tests that simulate_rate_limit() and generate_error_response(429)
              return rate limit error with proper message, headers, and documentation URL.

        How: Creates rate limit error response, validates it includes rate limit
             specific message, headers, and GitHub documentation URL.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Act - Test both methods
        error_response1 = simulator.generate_error_response(429)
        error_response2 = simulator.simulate_rate_limit()

        # Assert both methods produce same result
        for error_response in [error_response1, error_response2]:
            assert error_response is not None
            assert error_response["status_code"] == 429
            assert "headers" in error_response
            assert "response_data" in error_response

            # Check headers
            headers = error_response["headers"]
            assert "X-RateLimit-Limit" in headers
            assert "X-RateLimit-Remaining" in headers
            assert "X-RateLimit-Reset" in headers
            assert "Retry-After" in headers

            # Check response body
            response_data = error_response["response_data"]
            assert "API rate limit exceeded" in response_data["message"]
            assert "documentation_url" in response_data
            assert "rate-limiting" in response_data["documentation_url"]

    def test_error_tracking(self) -> None:
        """
        Why: Ensure request counter accurately tracks error simulation attempts
             for debugging and metrics collection in test scenarios.

        What: Tests that request_count increments with each should_simulate_error()
              call and track_error() properly records error counts.

        How: Makes multiple calls to should_simulate_error() and track_error(),
             verifies counters increment correctly.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(0.0, [500])  # No errors

        path = "/test/path"

        # Act - Test request counting
        initial_count = simulator.request_count
        for i in range(5):
            simulator.should_simulate_error(path)
            assert simulator.request_count == initial_count + i + 1

        # Assert
        assert simulator.request_count == initial_count + 5

        # Test error tracking
        simulator.track_error(500)
        simulator.track_error(502)
        simulator.track_error(500)

        assert simulator.total_error_count == 3
        assert simulator.error_count[500] == 2
        assert simulator.error_count[502] == 1

    def test_get_metrics(self) -> None:
        """
        Why: Verify error simulator can provide metrics about generated errors
             for test analysis and debugging of error handling code.

        What: Tests that get_metrics() returns comprehensive metrics about
              number of requests, errors generated, and error rates.

        How: Generates errors, tracks them, then verifies metrics correctly
             reflect the counts and rates.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(1.0, [500])  # Always error

        path = "/test/path"

        # Act - Generate requests and track errors
        for _ in range(10):
            should_error, status_code = simulator.should_simulate_error(path)
            if should_error:
                simulator.track_error(status_code)

        # Get metrics
        metrics = simulator.get_metrics()

        # Assert
        assert metrics["total_requests"] == 10
        assert metrics["total_errors"] == 10  # All should be errors with rate 1.0
        assert metrics["error_rate"] == 1.0
        assert 500 in metrics["error_counts"]

        # Reset and test with no errors
        simulator.reset()
        simulator.configure_error_simulation(0.0, [500])

        for _ in range(10):
            should_error, status_code = simulator.should_simulate_error(path)
            if should_error:
                simulator.track_error(status_code)

        metrics = simulator.get_metrics()
        assert metrics["total_requests"] == 10
        assert metrics["total_errors"] == 0  # No errors with rate 0.0
        assert metrics["error_rate"] == 0.0

    def test_path_specific_errors(self) -> None:
        """
        Why: Ensure specific endpoints can be configured for targeted error injection
             to test error handling for particular API operations.

        What: Tests configure_endpoint_errors() and path matching logic for
              endpoint-specific error generation with frequency control.

        How: Configures errors for specific endpoint pattern, makes requests
             and verifies errors occur at configured frequency.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_endpoint_errors(
            "/repos/{owner}/{repo}/pulls", 503, frequency=3
        )

        path = "/repos/test/myrepo/pulls"

        # Act - Make requests and track errors
        errors = []
        for _i in range(9):
            should_error, status_code = simulator.should_simulate_error(path)
            errors.append((should_error, status_code))

        # Assert - Errors should occur at positions 2, 5, 8 (every 3rd request, 0-indexed)
        assert errors[2][0] is True  # 3rd request (index 2)
        assert errors[2][1] == 503

        assert errors[5][0] is True  # 6th request (index 5)
        assert errors[5][1] == 503

        assert errors[8][0] is True  # 9th request (index 8)
        assert errors[8][1] == 503

        # Non-error positions should be False
        assert errors[0][0] is False
        assert errors[1][0] is False
        assert errors[3][0] is False
        assert errors[4][0] is False
        assert errors[6][0] is False
        assert errors[7][0] is False

    def test_error_response_format(self) -> None:
        """
        Why: Verify error responses match GitHub API format for compatibility
             with GitHub client error handling code.

        What: Tests that error responses have correct JSON structure matching
              GitHub API error response format with headers and body.

        How: Creates various error responses and validates they contain
             expected fields and structure for GitHub API compatibility.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Test various error codes
        test_codes = [429, 500, 502, 503, 504]

        for code in test_codes:
            # Act
            error_response = simulator.generate_error_response(code)

            # Assert
            assert error_response is not None
            assert "status_code" in error_response
            assert "headers" in error_response
            assert "response_data" in error_response
            assert error_response["status_code"] == code

            # Check headers
            headers = error_response["headers"]
            assert isinstance(headers, dict)
            assert "X-GitHub-Request-Id" in headers or "X-RateLimit-Limit" in headers

            # Check response body
            response_data = error_response["response_data"]
            assert "message" in response_data
            assert isinstance(response_data["message"], str)
            assert len(response_data["message"]) > 0
            assert "documentation_url" in response_data

    def test_pattern_matching(self) -> None:
        """
        Why: Ensure path pattern matching correctly identifies endpoints for
             targeted error injection in specific API operations.

        What: Tests _matches_pattern() method with various patterns and paths
              to verify pattern matching logic works correctly.

        How: Tests pattern matching with owner, repo, pr_number, and ref
             placeholders against actual paths using regex matching.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Test cases: (pattern, path, should_match)
        # Note: The pattern matching uses re.match which checks from the beginning
        # but doesn't require exact match to end (it's a prefix match)
        # Only these placeholders are supported: {owner}, {repo}, {pr_number}, {ref}
        test_cases = [
            ("/repos/{owner}/{repo}", "/repos/octocat/hello-world", True),
            (
                "/repos/{owner}/{repo}",
                "/repos/octocat/hello-world/pulls",
                True,
            ),  # Prefix match
            ("/repos/{owner}/{repo}/pulls", "/repos/octocat/hello-world/pulls", True),
            (
                "/repos/{owner}/{repo}/pulls/{pr_number}",
                "/repos/octocat/hello-world/pulls/123",
                True,
            ),
            (
                "/repos/{owner}/{repo}/pulls/{pr_number}",
                "/repos/octocat/hello-world/pulls",
                False,
            ),
            (
                "/repos/{owner}/{repo}/commits/{ref}/check-runs",
                "/repos/octocat/hello-world/commits/abc123/check-runs",
                True,
            ),
            (
                "/repos/{owner}/{repo}/commits/{ref}/check-runs",
                "/repos/octocat/hello-world/commits",
                False,
            ),
            # Test with refs and other valid placeholders
            (
                "/repos/{owner}/{repo}/branches/{ref}",
                "/repos/octocat/hello-world/branches/main",
                True,
            ),
            (
                "/repos/{owner}/{repo}/issues/{pr_number}/comments",
                "/repos/octocat/hello-world/issues/42/comments",
                True,
            ),
        ]

        for pattern, path, should_match in test_cases:
            # Act
            result = simulator._matches_pattern(path, pattern)

            # Assert
            assert result == should_match, (
                f"Pattern '{pattern}' vs path '{path}' - expected {should_match}, got {result}"
            )

    def test_reset_functionality(self) -> None:
        """
        Why: Ensure simulator can be reset between test runs for proper test
             isolation and clean state management.

        What: Tests that reset() method clears request counter, error counts,
              and allows fresh configuration for new test scenarios.

        How: Configures simulator, generates requests and errors, resets,
             and verifies counters are cleared.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(0.5, [500, 502])

        path = "/test/path"

        # Generate some requests and track errors
        for _ in range(5):
            simulator.should_simulate_error(path)

        simulator.track_error(500)
        simulator.track_error(502)

        assert simulator.request_count == 5
        assert simulator.total_error_count == 2

        # Act - Reset
        simulator.reset()

        # Assert
        assert simulator.request_count == 0
        assert simulator.total_error_count == 0
        assert len(simulator.error_count) == 0

        # Verify configuration is retained (design choice)
        assert simulator.error_rate == 0.5
        assert simulator.error_codes == [500, 502]

        # Can still generate errors after reset
        should_error, status_code = simulator.should_simulate_error(path)
        assert simulator.request_count == 1

    def test_multiple_endpoint_patterns(self) -> None:
        """
        Why: Verify simulator can handle multiple endpoint-specific error configurations
             for complex testing scenarios with different error behaviors per endpoint.

        What: Tests configuring different error codes and frequencies for multiple
              endpoint patterns and verifies correct error injection.

        How: Configures errors for different endpoints, makes requests to each,
             and validates appropriate errors are generated.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Configure different errors for different endpoints
        simulator.configure_endpoint_errors(
            "/repos/{owner}/{repo}/pulls", 502, frequency=2
        )
        simulator.configure_endpoint_errors(
            "/repos/{owner}/{repo}/commits/{ref}/check-runs", 503, frequency=3
        )

        pulls_path = "/repos/test/repo/pulls"
        checks_path = "/repos/test/repo/commits/abc123/check-runs"

        # Act - Test pulls endpoint (every 2nd request)
        pulls_errors = []
        for _ in range(4):
            should_error, status_code = simulator.should_simulate_error(pulls_path)
            pulls_errors.append((should_error, status_code))

        # Act - Test checks endpoint (every 3rd request)
        checks_errors = []
        for _ in range(6):
            should_error, status_code = simulator.should_simulate_error(checks_path)
            checks_errors.append((should_error, status_code))

        # Assert - Pulls endpoint errors (request count 2, 4)
        assert pulls_errors[1][0] is True and pulls_errors[1][1] == 502  # 2nd request
        assert pulls_errors[3][0] is True and pulls_errors[3][1] == 502  # 4th request
        assert pulls_errors[0][0] is False  # 1st request
        assert pulls_errors[2][0] is False  # 3rd request

        # Assert - Checks endpoint errors (request count 7, 10 - continuing from pulls)
        # Note: request_count is global, so 7th and 10th requests overall
        assert checks_errors[2][0] is False  # 7th request overall, not divisible by 3
        assert checks_errors[5][0] is False  # 10th request overall, not divisible by 3

    def test_error_code_selection(self) -> None:
        """
        Why: Ensure simulator randomly selects from configured error codes to
             provide variety in error testing scenarios.

        What: Tests that when multiple error codes are configured, the simulator
              randomly selects from them for error responses.

        How: Configures multiple error codes, generates many errors with fixed seed,
             and verifies all configured codes are used.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(1.0, [500, 502, 503])  # Always error

        path = "/test/path"

        # Use fixed seed for reproducible randomness
        random.seed(12345)

        # Act - Generate many errors to see variety
        error_codes_seen = set()
        for _ in range(30):
            should_error, status_code = simulator.should_simulate_error(path)
            if should_error:
                error_codes_seen.add(status_code)

        # Assert - All configured codes should be used
        assert 500 in error_codes_seen
        assert 502 in error_codes_seen
        assert 503 in error_codes_seen

    def test_zero_error_rate(self) -> None:
        """
        Why: Ensure simulator can be completely disabled for normal operation testing
             without any error injection.

        What: Tests that with 0.0 error rate, no errors are ever generated
              regardless of number of requests.

        How: Configures 0.0 error rate, makes many requests, and verifies
             no errors are generated.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(0.0, [500, 502, 503])

        path = "/test/path"

        # Act - Make many requests
        errors_generated = False
        for _ in range(100):
            should_error, status_code = simulator.should_simulate_error(path)
            if should_error:
                errors_generated = True
                break

        # Assert
        assert not errors_generated
        assert simulator.request_count == 100

    def test_hundred_percent_error_rate(self) -> None:
        """
        Why: Ensure simulator can generate errors for every request when testing
             complete service failure scenarios.

        What: Tests that with 1.0 error rate, every request generates an error
              without exceptions.

        How: Configures 1.0 error rate, makes many requests, and verifies
             all generate errors.
        """
        # Arrange
        simulator = ErrorSimulator()
        simulator.configure_error_simulation(1.0, [500])

        path = "/test/path"

        # Act - Make many requests
        all_errors = True
        for _ in range(100):
            should_error, status_code = simulator.should_simulate_error(path)
            if not should_error:
                all_errors = False
                break

        # Assert
        assert all_errors
        assert simulator.request_count == 100

    def test_unknown_error_codes(self) -> None:
        """
        Why: Ensure simulator handles non-standard HTTP error codes gracefully
             for testing edge cases and unusual error scenarios.

        What: Tests that generate_error_response() generates appropriate default
              message for unknown error codes.

        How: Creates error responses for non-standard codes and verifies
             they have generic but valid error format.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Test non-standard error codes
        test_codes = [418, 420, 499, 599]

        for code in test_codes:
            # Act
            error_response = simulator.generate_error_response(code)

            # Assert
            assert error_response is not None
            assert error_response["status_code"] == code
            assert "headers" in error_response
            assert "response_data" in error_response
            assert "message" in error_response["response_data"]
            assert error_response["response_data"]["message"] == f"HTTP {code} Error"
            assert "documentation_url" in error_response["response_data"]

    def test_endpoint_priority_over_random(self) -> None:
        """
        Why: Ensure endpoint-specific errors take precedence over random error rate
             for precise control in targeted testing scenarios.

        What: Tests that when both endpoint-specific and random errors are configured,
              endpoint-specific configuration is checked first.

        How: Configures both endpoint-specific and random errors, verifies endpoint
             errors occur at exact frequency regardless of random rate.
        """
        # Arrange
        simulator = ErrorSimulator()

        # Configure random errors (low rate)
        simulator.configure_error_simulation(0.1, [500])

        # Configure specific endpoint errors (deterministic)
        simulator.configure_endpoint_errors(
            "/repos/{owner}/{repo}/pulls", 503, frequency=2
        )

        path = "/repos/test/repo/pulls"

        # Use fixed seed to control random behavior
        random.seed(99999)

        # Act - Make requests
        errors = []
        for _ in range(4):
            should_error, status_code = simulator.should_simulate_error(path)
            errors.append((should_error, status_code))

        # Assert - Endpoint errors should occur exactly at frequency 2
        assert errors[1][0] is True and errors[1][1] == 503  # 2nd request
        assert errors[3][0] is True and errors[3][1] == 503  # 4th request

        # First and third requests should follow random rate (likely False with 0.1 rate)
        # but we're mainly testing that endpoint errors are deterministic
