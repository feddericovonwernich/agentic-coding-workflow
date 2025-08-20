#!/usr/bin/env python3
"""
Mock GitHub API Server for Testing

This server provides realistic GitHub API responses using real data
collected from the GitHub API. It eliminates the need for actual
GitHub tokens in integration tests.

Usage:
    python tests/fixtures/github/mock_server.py [--port 8080]
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from flask import Flask, Response, jsonify, request


class MockGitHubServer:
    """
    Mock GitHub API server that serves realistic responses.

    Why: Provide realistic GitHub API responses for integration testing
         without requiring actual GitHub tokens or external dependencies.
    What: Flask-based HTTP server that mimics GitHub API endpoints
          with real response data collected from GitHub API.
    How: Serves static responses from JSON files and generates dynamic
         responses for arbitrary requests with realistic data structures.
    """

    def __init__(self, responses_dir: Path) -> None:
        self.app = Flask(__name__)
        self.responses_dir = responses_dir
        self._setup_routes()

        # Cache for loaded responses
        self._response_cache: dict[str, Any] = {}

    def _setup_routes(self) -> None:
        """
        Why: Configure Flask routes to match GitHub API endpoint patterns
             for comprehensive API simulation.
        What: Sets up all the API routes that mirror GitHub REST API.
        How: Defines route handlers for user, repo, rate limit, and other endpoints.
        """

        @self.app.route("/")
        def root():
            return jsonify(
                {
                    "message": "GitHub API Mock Server",
                    "documentation_url": "https://docs.github.com/rest",
                }
            )

        @self.app.route("/user")
        def get_user() -> Response:
            """
            Why: Provide authenticated user endpoint for testing authentication flows.
            What: Returns authenticated user information from static response.
            How: Serves user.json response file with realistic user data.
            """
            return self._serve_response("user.json")

        @self.app.route("/rate_limit")
        def get_rate_limit() -> Response:
            """
            Why: Provide rate limit endpoint for testing rate limiting logic.
            What: Returns API rate limit information from static response.
            How: Serves rate_limit.json with realistic GitHub rate limit data.
            """
            return self._serve_response("rate_limit.json")

        @self.app.route("/repos/<owner>/<repo>")
        def get_repository(owner: str, repo: str) -> Response:
            """
            Why: Support repository endpoint for testing repository operations
                 with both static and dynamic responses.
            What: Returns repository information based on owner/repo parameters.
            How: Serves static responses for known repos, generates dynamic responses
                 for arbitrary repos, returns 404 for test error scenarios.
            """
            if owner == "octocat" and repo == "Hello-World":
                return self._serve_response("repo_octocat_hello-world.json")
            elif owner == "nonexistent-user" and repo == "nonexistent-repo":
                return self._serve_error_response("404_nonexistent_repo.json", 404)
            else:
                # Generate a dynamic repository response based on the request
                return self._generate_repo_response(owner, repo)

        @self.app.route("/repos/<owner>/<repo>/pulls")
        def get_pulls(owner: str, repo: str) -> Response:
            """
            Why: Support pull requests endpoint for testing PR-related functionality.
            What: Returns pull request list for specified repository.
            How: Serves static PR data for known repos, empty list for others.
            """
            if owner == "microsoft" and repo == "vscode":
                return self._serve_response("pulls_microsoft_vscode.json")
            else:
                # Return empty pulls list for other repos
                return jsonify([])

        @self.app.route("/users/<username>/repos")
        def get_user_repos(username: str) -> Response:
            """
            Why: Support user repositories endpoint for testing pagination.
            What: Returns repository list for specified user.
            How: Serves static repos for known users, generates repos for pagination
                 testing, empty list for others.
            """
            if username == "octocat":
                return self._serve_response("repos_octocat.json")
            elif username == "torvalds":
                # For pagination testing - simulate Linus Torvalds repos
                return self._generate_user_repos_response(username)
            else:
                return jsonify([])

        @self.app.route("/repos/<owner>/<repo>/commits/<ref>/check-runs")
        def get_check_runs(owner: str, repo: str, ref: str) -> Response:
            """
            Why: Support check runs endpoint for testing CI/CD integration features.
            What: Returns check runs for specified repository and commit reference.
            How: Serves static check runs for known repos, empty response for others.
            """
            if owner == "microsoft" and repo == "vscode" and ref == "main":
                return self._serve_response("check_runs_microsoft_vscode_main.json")
            else:
                # Return empty check runs for other requests
                return jsonify({"total_count": 0, "check_runs": []})

        @self.app.errorhandler(404)
        def not_found(error) -> Response:
            """
            Why: Provide realistic 404 error responses matching GitHub API format.
            What: Handles 404 errors with GitHub-like error response.
            How: Returns JSON error response with message and documentation URL.
            """
            return jsonify(
                {
                    "message": "Not Found",
                    "documentation_url": "https://docs.github.com/rest",
                }
            ), 404

    def _serve_response(self, filename: str) -> Response:
        """Serve a response from the cached JSON files."""
        if filename not in self._response_cache:
            file_path = self.responses_dir / filename
            if file_path.exists():
                with open(file_path) as f:
                    self._response_cache[filename] = json.load(f)
            else:
                return jsonify({"error": f"Response file {filename} not found"}), 500

        response_data = self._response_cache[filename]

        # Handle pagination if requested
        response_data = self._handle_pagination(response_data)

        # Add realistic headers
        response = jsonify(response_data)
        self._add_github_headers(response)
        return response

    def _serve_error_response(
        self, filename: str, status_code: int
    ) -> tuple[Response, int]:
        """Serve an error response."""
        if filename not in self._response_cache:
            file_path = self.responses_dir / filename
            if file_path.exists():
                with open(file_path) as f:
                    content = f.read().strip()
                    # Handle the case where gh CLI adds extra text
                    if content.startswith("{"):
                        # Extract just the JSON part
                        json_end = content.find("}")
                        if json_end > 0:
                            json_content = content[: json_end + 1]
                            self._response_cache[filename] = json.loads(json_content)
                        else:
                            self._response_cache[filename] = json.loads(content)
                    else:
                        self._response_cache[filename] = {"message": "Not Found"}
            else:
                self._response_cache[filename] = {"message": "Not Found"}

        response = jsonify(self._response_cache[filename])
        self._add_github_headers(response)
        return response, status_code

    def _handle_pagination(self, data: Any) -> Any:
        """Handle pagination parameters."""
        if not isinstance(data, list):
            return data

        # Get pagination parameters
        per_page = int(request.args.get("per_page", 30))
        page = int(request.args.get("page", 1))

        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page

        return data[start_idx:end_idx]

    def _generate_repo_response(self, owner: str, repo: str) -> Response:
        """Generate a dynamic repository response."""
        repo_data = {
            "id": hash(f"{owner}/{repo}") % 1000000,
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "owner": {"login": owner, "id": hash(owner) % 1000000, "type": "User"},
            "private": False,
            "html_url": f"https://github.com/{owner}/{repo}",
            "description": f"Mock repository for {owner}/{repo}",
            "fork": False,
            "url": f"https://api.github.com/repos/{owner}/{repo}",
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "pushed_at": "2023-06-01T00:00:00Z",
            "stargazers_count": 10,
            "watchers_count": 10,
            "language": "Python",
            "forks_count": 2,
            "open_issues_count": 1,
            "default_branch": "main",
        }

        response = jsonify(repo_data)
        self._add_github_headers(response)
        return response

    def _generate_user_repos_response(self, username: str) -> Response:
        """Generate a dynamic user repositories response."""
        # Simulate multiple repositories for pagination testing
        repos = []
        for i in range(1, 101):  # Generate 100 repos for pagination testing
            repo_data = {
                "id": i,
                "name": f"repo-{i}",
                "full_name": f"{username}/repo-{i}",
                "owner": {
                    "login": username,
                    "id": hash(username) % 1000000,
                    "type": "User",
                },
                "private": False,
                "description": f"Repository {i} for {username}",
                "fork": False,
                "created_at": f"2020-{i:02d}-01T00:00:00Z",
                "stargazers_count": i,
                "language": "Python" if i % 2 == 0 else "JavaScript",
            }
            repos.append(repo_data)

        # Handle pagination
        paginated_repos = self._handle_pagination(repos)

        response = jsonify(paginated_repos)
        self._add_github_headers(response)
        return response

    def _add_github_headers(self, response: Response) -> None:
        """
        Why: Ensure responses include GitHub-like headers for testing rate limiting
             and other header-dependent client functionality.
        What: Adds realistic GitHub API headers to all responses.
        How: Sets rate limit headers, server info, and content type headers.
        """
        response.headers["X-RateLimit-Limit"] = "5000"
        response.headers["X-RateLimit-Remaining"] = "4999"
        response.headers["X-RateLimit-Reset"] = "1640995200"
        response.headers["X-GitHub-Media-Type"] = "github.v3; format=json"
        response.headers["Server"] = "GitHub.com"
        response.headers["Access-Control-Allow-Origin"] = "*"

    def run(self, host: str = "0.0.0.0", port: int = 8080, debug: bool = False) -> None:
        """
        Why: Provide simple interface to start the mock server for testing scenarios.
        What: Starts the Flask server with specified configuration.
        How: Runs Flask development server with host, port, and debug settings.
        """
        print(f"🚀 Starting Mock GitHub API Server on {host}:{port}")
        print(f"📁 Serving responses from: {self.responses_dir}")
        self.app.run(host=host, port=port, debug=debug)


def main():
    """Main entry point for the mock server."""
    parser = argparse.ArgumentParser(description="Mock GitHub API Server")
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8080,
        help="Port to run the server on (default: 8080)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    # Find the responses directory
    responses_dir = Path(__file__).parent / "responses"
    if not responses_dir.exists():
        print(f"❌ Error: Responses directory not found: {responses_dir}")
        print("Run the response collection script first!")
        return 1

    # Create and run the server
    server = MockGitHubServer(responses_dir)
    try:
        server.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        print("\n👋 Mock GitHub API Server stopped")

    return 0


if __name__ == "__main__":
    exit(main())
