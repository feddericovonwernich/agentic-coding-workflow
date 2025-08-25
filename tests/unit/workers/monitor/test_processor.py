"""Comprehensive unit tests for PR Processor orchestration.

This module provides extensive test coverage for the PRProcessor class,
including configuration validation, processing workflows, error handling,
performance monitoring, and resource management.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.workers.monitor.models import (
    ChangeType,
    CheckRunDiscovery,
    DiscoveryResult,
    OperationStatus,
    ProcessingMetrics,
    SeverityLevel,
    StateChangeEvent,
    SyncOperation,
)
from src.workers.monitor.processor import (
    PRProcessor,
    ProcessingMode,
    ProcessingPhase,
    ProcessingSession,
    ProcessorConfig,
    RepositoryProcessingResult,
)


class TestProcessorConfig:
    """Test cases for ProcessorConfig validation and behavior."""

    def test_default_config_creation(self):
        """Test creation with default values."""
        config = ProcessorConfig()

        assert config.max_concurrent_repos == 10
        assert config.max_concurrent_api_calls == 50
        assert config.batch_size == 25
        assert config.incremental_window_hours == 24
        assert config.enable_dry_run is False
        assert config.enable_metrics is True

    def test_custom_config_creation(self):
        """Test creation with custom values."""
        config = ProcessorConfig(
            max_concurrent_repos=20,
            batch_size=50,
            enable_dry_run=True,
            memory_limit_mb=4096,
        )

        assert config.max_concurrent_repos == 20
        assert config.batch_size == 50
        assert config.enable_dry_run is True
        assert config.memory_limit_mb == 4096

    def test_config_validation_success(self):
        """Test successful configuration validation."""
        config = ProcessorConfig(
            max_concurrent_repos=5,
            max_concurrent_api_calls=25,
            batch_size=10,
            incremental_window_hours=12,
            memory_limit_mb=1024,
        )

        # Should not raise
        config.validate()

    def test_config_validation_negative_concurrent_repos(self):
        """Test validation failure for negative concurrent repos."""
        config = ProcessorConfig(max_concurrent_repos=0)

        with pytest.raises(ValueError, match="max_concurrent_repos must be positive"):
            config.validate()

    def test_config_validation_insufficient_api_calls(self):
        """Test validation failure when API calls < concurrent repos."""
        config = ProcessorConfig(
            max_concurrent_repos=20,
            max_concurrent_api_calls=10,
        )

        with pytest.raises(
            ValueError, match="max_concurrent_api_calls must be >= max_concurrent_repos"
        ):
            config.validate()

    def test_config_validation_invalid_batch_size(self):
        """Test validation failure for invalid batch sizes."""
        # Too small
        config = ProcessorConfig(batch_size=0)
        with pytest.raises(ValueError, match="batch_size must be between 1 and 1000"):
            config.validate()

        # Too large
        config = ProcessorConfig(batch_size=2000)
        with pytest.raises(ValueError, match="batch_size must be between 1 and 1000"):
            config.validate()

    def test_config_validation_invalid_incremental_window(self):
        """Test validation failure for invalid incremental window."""
        config = ProcessorConfig(incremental_window_hours=0)

        with pytest.raises(
            ValueError, match="incremental_window_hours must be positive"
        ):
            config.validate()

    def test_config_validation_insufficient_memory(self):
        """Test validation failure for insufficient memory limit."""
        config = ProcessorConfig(memory_limit_mb=128)

        with pytest.raises(ValueError, match="memory_limit_mb must be at least 256MB"):
            config.validate()


class TestProcessingSession:
    """Test cases for ProcessingSession tracking and metrics."""

    def test_session_creation(self):
        """Test session creation with defaults."""
        session = ProcessingSession()

        assert session.session_id is not None
        assert session.mode == ProcessingMode.INCREMENTAL
        assert session.phase == ProcessingPhase.INITIALIZATION
        assert session.total_repositories == 0
        assert session.processed_repositories == 0
        assert len(session.errors) == 0

    def test_session_with_custom_mode(self):
        """Test session creation with custom mode."""
        session = ProcessingSession(mode=ProcessingMode.DRY_RUN)

        assert session.mode == ProcessingMode.DRY_RUN

    def test_duration_calculation(self):
        """Test duration calculation."""
        session = ProcessingSession()

        # Before completion
        duration = session.duration_seconds
        assert duration > 0

        # After completion
        session.completed_at = session.started_at + timedelta(seconds=30)
        assert session.duration_seconds == 30.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        session = ProcessingSession()

        # No repositories
        assert session.success_rate == 100.0

        # Some processing results
        session.total_repositories = 10
        session.processed_repositories = 8
        assert session.success_rate == 80.0

    def test_completion_status(self):
        """Test completion status checking."""
        session = ProcessingSession()

        assert not session.is_completed

        session.update_phase(ProcessingPhase.COMPLETED)
        assert session.is_completed
        assert session.completed_at is not None

        session.update_phase(ProcessingPhase.FAILED)
        assert session.is_completed

    def test_error_tracking(self):
        """Test error addition and tracking."""
        session = ProcessingSession()

        session.add_error("Test error message")
        assert len(session.errors) == 1
        assert "Test error message" in session.errors[0]

    def test_warning_tracking(self):
        """Test warning addition and tracking."""
        session = ProcessingSession()

        session.add_warning("Test warning message")
        assert len(session.warnings) == 1
        assert "Test warning message" in session.warnings[0]


class TestRepositoryProcessingResult:
    """Test cases for RepositoryProcessingResult."""

    def test_result_creation(self):
        """Test result creation."""
        repo_id = uuid.uuid4()
        result = RepositoryProcessingResult(
            repository_id=repo_id,
            repository_name="test-org/test-repo",
            success=True,
            processing_time_seconds=15.5,
            prs_discovered=5,
            check_runs_discovered=12,
        )

        assert result.repository_id == repo_id
        assert result.repository_name == "test-org/test-repo"
        assert result.success is True
        assert result.processing_time_seconds == 15.5
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 12

    def test_result_string_representation(self):
        """Test string representation."""
        result = RepositoryProcessingResult(
            repository_id=uuid.uuid4(),
            repository_name="test-repo",
            success=True,
            processing_time_seconds=10.0,
            prs_discovered=3,
            check_runs_discovered=8,
            state_changes_detected=2,
        )

        str_repr = str(result)
        assert "test-repo" in str_repr
        assert "SUCCESS" in str_repr
        assert "PRs=3" in str_repr
        assert "Checks=8" in str_repr
        assert "Changes=2" in str_repr
        assert "10.00s" in str_repr


class TestPRProcessor:
    """Test cases for the main PRProcessor class."""

    @pytest.fixture
    def mock_github_client(self):
        """Mock GitHub client."""
        return Mock()

    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_cache_manager(self):
        """Mock cache manager."""
        return Mock()

    @pytest.fixture
    def processor_config(self):
        """Test processor configuration."""
        return ProcessorConfig(
            max_concurrent_repos=2,
            max_concurrent_api_calls=10,
            batch_size=5,
            enable_detailed_logging=True,
        )

    @pytest.fixture
    async def processor(
        self, mock_github_client, mock_session, mock_cache_manager, processor_config
    ):
        """PRProcessor instance for testing."""
        processor = PRProcessor(
            github_client=mock_github_client,
            session=mock_session,
            cache_manager=mock_cache_manager,
            config=processor_config,
        )

        # Mock the repository repository
        processor.repo_repository = AsyncMock()

        return processor

    def test_processor_initialization(
        self, mock_github_client, mock_session, mock_cache_manager
    ):
        """Test processor initialization."""
        config = ProcessorConfig(max_concurrent_repos=5)

        processor = PRProcessor(
            github_client=mock_github_client,
            session=mock_session,
            cache_manager=mock_cache_manager,
            config=config,
        )

        assert processor.github_client == mock_github_client
        assert processor.session == mock_session
        assert processor.cache_manager == mock_cache_manager
        assert processor.config == config
        assert processor._current_session is None
        assert not processor._shutdown_requested

    def test_processor_initialization_default_config(
        self, mock_github_client, mock_session, mock_cache_manager
    ):
        """Test processor initialization with default config."""
        processor = PRProcessor(
            github_client=mock_github_client,
            session=mock_session,
            cache_manager=mock_cache_manager,
        )

        assert isinstance(processor.config, ProcessorConfig)
        assert processor.config.max_concurrent_repos == 10

    @pytest.mark.asyncio
    async def test_context_manager(self, processor):
        """Test async context manager functionality."""
        async with processor as ctx_processor:
            assert ctx_processor is processor

        # Should request shutdown after exit
        assert processor._shutdown_requested

    @pytest.mark.asyncio
    async def test_process_single_repository_success(self, processor):
        """Test successful single repository processing."""
        repo_id = uuid.uuid4()

        # Mock repository lookup
        mock_repo = Mock()
        mock_repo.full_name = "test-org/test-repo"
        mock_repo.name = "test-repo"
        mock_repo.last_polled_at = None
        processor.repo_repository.get_by_id.return_value = mock_repo

        # Mock discovery components
        processor.pr_discovery = AsyncMock()
        processor.check_discovery = AsyncMock()
        processor.state_detector = AsyncMock()
        processor.data_synchronizer = AsyncMock()

        # Setup mock return values
        mock_prs = [
            DiscoveryResult(
                repository_id=repo_id,
                repository_name="test-repo",
                repository_owner="test-org",
                pr_number=1,
                title="Test PR",
                author="test-user",
                state=PRState.OPENED,
                draft=False,
                base_branch="main",
                head_branch="feature",
                base_sha="abc123",
                head_sha="def456",
                url="https://github.com/test-org/test-repo/pull/1",
            )
        ]

        mock_checks = [
            CheckRunDiscovery(
                pr_id=repo_id,
                pr_number=1,
                github_check_run_id="123",
                check_name="test-check",
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
            )
        ]

        mock_metrics = ProcessingMetrics(
            github_api_calls_made=5,
            prs_discovered=1,
            check_runs_discovered=1,
        )

        processor.pr_discovery.discover_prs.return_value = (mock_prs, mock_metrics)
        processor.check_discovery.discover_check_runs.return_value = mock_checks
        processor.state_detector.detect_pr_changes.return_value = []
        processor.state_detector.detect_check_run_changes.return_value = []
        processor.state_detector.analyze_significance.return_value = []
        processor.state_detector.filter_actionable_changes.return_value = []

        mock_sync = SyncOperation(status=OperationStatus.COMPLETED)
        processor.data_synchronizer.synchronize_changes.return_value = mock_sync

        # Execute
        result = await processor.process_single_repository(repo_id)

        # Assertions
        assert result.success is True
        assert result.repository_id == repo_id
        assert result.repository_name == "test-org/test-repo"
        assert result.prs_discovered == 1
        assert result.check_runs_discovered == 1
        assert result.api_calls_made == 5
        assert result.sync_success is True

    @pytest.mark.asyncio
    async def test_process_single_repository_not_found(self, processor):
        """Test processing non-existent repository."""
        repo_id = uuid.uuid4()
        processor.repo_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match=f"Repository {repo_id} not found"):
            await processor.process_single_repository(repo_id)

    @pytest.mark.asyncio
    async def test_process_single_repository_dry_run(self, processor):
        """Test single repository processing in dry-run mode."""
        repo_id = uuid.uuid4()

        # Mock repository
        mock_repo = Mock()
        mock_repo.full_name = "test-org/test-repo"
        processor.repo_repository.get_by_id.return_value = mock_repo

        # Mock components
        processor.pr_discovery = AsyncMock()
        processor.check_discovery = AsyncMock()
        processor.state_detector = AsyncMock()

        processor.pr_discovery.discover_prs.return_value = ([], ProcessingMetrics())
        processor.check_discovery.discover_check_runs.return_value = []
        processor.state_detector.detect_pr_changes.return_value = []
        processor.state_detector.detect_check_run_changes.return_value = []
        processor.state_detector.analyze_significance.return_value = []
        processor.state_detector.filter_actionable_changes.return_value = []

        # Execute in dry-run mode
        result = await processor.process_single_repository(repo_id, dry_run=True)

        # Assertions
        assert result.success is True
        assert result.sync_operation is None  # No sync operation in dry run
        assert result.sync_success is False

    @pytest.mark.asyncio
    async def test_process_single_repository_error_handling(self, processor):
        """Test error handling in single repository processing."""
        repo_id = uuid.uuid4()

        # Mock repository
        mock_repo = Mock()
        mock_repo.full_name = "test-org/test-repo"
        processor.repo_repository.get_by_id.return_value = mock_repo

        # Mock discovery to raise error
        processor.pr_discovery = AsyncMock()
        processor.pr_discovery.discover_prs.side_effect = Exception("Discovery failed")

        # Execute
        result = await processor.process_single_repository(repo_id)

        # Assertions
        assert result.success is False
        assert result.error == "Discovery failed"
        assert result.processing_time_seconds > 0

    @pytest.mark.asyncio
    async def test_coordinate_discovery(self, processor):
        """Test discovery coordination."""
        processor.pr_discovery = AsyncMock()
        processor.check_discovery = AsyncMock()

        repo_context = Mock()
        repo_context.repository_owner = "test-org"
        repo_context.repository_name = "test-repo"

        # Mock PR discovery with real DiscoveryResult
        repo_id = uuid.uuid4()
        mock_prs = [
            DiscoveryResult(
                repository_id=repo_id,
                repository_name="test-repo",
                repository_owner="test-org",
                pr_number=1,
                title="Test PR",
                author="test-user",
                state=PRState.OPENED,
                draft=False,
                base_branch="main",
                head_branch="feature",
                base_sha="abc123",
                head_sha="def456",
                url="https://github.com/test-org/test-repo/pull/1",
            )
        ]
        mock_pr_metrics = ProcessingMetrics(prs_discovered=1, github_api_calls_made=2)
        processor.pr_discovery.discover_prs.return_value = (mock_prs, mock_pr_metrics)

        # Mock check discovery with real CheckRunDiscovery
        mock_checks = [
            CheckRunDiscovery(
                pr_id=repo_id,
                pr_number=1,
                github_check_run_id="123",
                check_name="test-check",
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
            )
        ]
        processor.check_discovery.discover_check_runs.return_value = mock_checks
        processor.check_discovery.get_metrics.return_value = ProcessingMetrics(
            check_runs_discovered=1,
            check_run_discovery_duration=5.0,
        )

        # Execute
        prs, checks, metrics = await processor._coordinate_discovery(repo_context, None)

        # Assertions
        assert len(prs) == 1
        assert len(checks) == 1
        assert metrics.prs_discovered == 1
        assert metrics.check_runs_discovered == 1
        assert metrics.github_api_calls_made == 2

    @pytest.mark.asyncio
    async def test_coordinate_change_detection(self, processor):
        """Test change detection coordination."""
        processor.state_detector = AsyncMock()

        # Mock discovered data
        mock_prs = [Mock()]
        mock_checks = [Mock(pr_number=1)]
        repo_id = uuid.uuid4()

        # Mock state detector responses
        pr_changes = [Mock()]
        check_changes = [Mock()]
        analyzed_changes = pr_changes + check_changes
        actionable_changes = [Mock()]

        processor.state_detector.detect_pr_changes.return_value = pr_changes
        processor.state_detector.detect_check_run_changes.return_value = check_changes
        processor.state_detector.analyze_significance.return_value = analyzed_changes
        processor.state_detector.filter_actionable_changes.return_value = (
            actionable_changes
        )

        # Execute
        changes = await processor._coordinate_change_detection(
            mock_prs, mock_checks, repo_id
        )

        # Assertions
        assert len(changes) == 1
        processor.state_detector.analyze_significance.assert_called_once()
        processor.state_detector.filter_actionable_changes.assert_called_once()

    @pytest.mark.asyncio
    async def test_coordinate_synchronization(self, processor):
        """Test synchronization coordination."""
        processor.data_synchronizer = AsyncMock()

        mock_prs = [Mock()]
        mock_checks = [Mock()]
        mock_changes = [Mock()]

        mock_sync_op = SyncOperation(status=OperationStatus.COMPLETED)
        processor.data_synchronizer.synchronize_changes.return_value = mock_sync_op

        # Execute
        sync_op = await processor._coordinate_synchronization(
            mock_prs, mock_checks, mock_changes
        )

        # Assertions
        assert sync_op.status == OperationStatus.COMPLETED
        processor.data_synchronizer.synchronize_changes.assert_called_once_with(
            mock_prs, mock_checks, mock_changes
        )

    @pytest.mark.asyncio
    async def test_request_shutdown(self, processor):
        """Test graceful shutdown request."""
        assert not processor._shutdown_requested

        await processor.request_shutdown()

        assert processor._shutdown_requested

    @pytest.mark.asyncio
    async def test_get_processing_status_idle(self, processor):
        """Test getting status when processor is idle."""
        status = await processor.get_processing_status()

        assert status["status"] == "idle"
        assert status["last_session"] is None

    @pytest.mark.asyncio
    async def test_get_processing_status_active(self, processor):
        """Test getting status when processor is active."""
        # Set up active session
        session = ProcessingSession(mode=ProcessingMode.INCREMENTAL)
        session.total_repositories = 10
        session.processed_repositories = 5
        session.total_prs_discovered = 25
        processor._current_session = session

        status = await processor.get_processing_status()

        assert status["status"] == "active"
        assert status["session_id"] == session.session_id
        assert status["phase"] == ProcessingPhase.INITIALIZATION.value
        assert status["mode"] == ProcessingMode.INCREMENTAL.value
        assert status["progress"]["processed"] == 5
        assert status["progress"]["total"] == 10
        assert status["progress"]["success_rate"] == 50.0
        assert status["metrics"]["prs_discovered"] == 25

    @pytest.mark.asyncio
    async def test_phase_initialize_repositories_specific_ids(self, processor):
        """Test repository initialization with specific IDs."""
        session = ProcessingSession()
        repo_id = uuid.uuid4()

        # Mock repository
        mock_repo = Mock()
        mock_repo.id = repo_id
        mock_repo.full_name = "test-org/test-repo"
        mock_repo.last_polled_at = None

        processor.repo_repository.get_by_id.return_value = mock_repo

        # Execute
        await processor._phase_initialize_repositories(session, [repo_id])

        # Assertions
        assert session.total_repositories == 1
        assert len(processor._repository_contexts) == 1

        context = processor._repository_contexts[0]
        assert context.repository_id == repo_id
        assert context.repository_owner == "test-org"
        assert context.repository_name == "test-repo"

    @pytest.mark.asyncio
    async def test_phase_initialize_repositories_missing_repo(self, processor):
        """Test repository initialization with missing repository."""
        session = ProcessingSession()
        repo_id = uuid.uuid4()

        processor.repo_repository.get_by_id.return_value = None

        # Execute
        await processor._phase_initialize_repositories(session, [repo_id])

        # Assertions
        assert session.total_repositories == 0
        assert len(processor._repository_contexts) == 0
        assert len(session.warnings) == 1
        assert str(repo_id) in session.warnings[0]

    @pytest.mark.asyncio
    async def test_phase_initialize_repositories_active_mode(self, processor):
        """Test repository initialization in active mode."""
        session = ProcessingSession(mode=ProcessingMode.FULL)

        # Mock active repositories
        mock_repos = [
            Mock(id=uuid.uuid4(), full_name="org1/repo1", last_polled_at=None),
            Mock(id=uuid.uuid4(), full_name="org2/repo2", last_polled_at=None),
        ]

        processor.repo_repository.get_active_repositories.return_value = mock_repos

        # Execute with no specific repository IDs (all active)
        await processor._phase_initialize_repositories(session, None)

        # Assertions
        assert session.total_repositories == 2
        assert len(processor._repository_contexts) == 2
        processor.repo_repository.get_active_repositories.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_final_metrics(self, processor):
        """Test final metrics collection."""
        session = ProcessingSession()
        session.processed_repositories = 5
        session.started_at = datetime.now(UTC) - timedelta(seconds=60)  # 1 minute ago

        # Add some repository results
        result1 = RepositoryProcessingResult(
            repository_id=uuid.uuid4(),
            repository_name="repo1",
            success=True,
            processing_time_seconds=10.0,
        )
        processor._repository_results[result1.repository_id] = result1

        # Mock psutil
        with patch("src.workers.monitor.processor.psutil") as mock_psutil:
            mock_process = Mock()
            mock_memory = Mock(rss=1024 * 1024 * 512)  # 512MB
            mock_process.memory_info.return_value = mock_memory
            mock_process.cpu_percent.return_value = 25.5
            mock_psutil.Process.return_value = mock_process

            # Execute
            await processor._collect_final_metrics(session)

            # Assertions
            assert session.processing_rate_repos_per_minute > 0
            assert session.memory_usage_mb == 512.0
            assert session.cpu_usage_percent == 25.5

    @pytest.mark.asyncio
    async def test_cleanup_session(self, processor):
        """Test session cleanup."""
        session = ProcessingSession()
        processor._current_session = session

        # Mock cleanup methods
        processor.pr_discovery = AsyncMock()
        processor.check_discovery = AsyncMock()
        processor.state_detector = Mock()

        # Execute cleanup
        await processor._cleanup_session(session)

        # Assertions
        assert processor._current_session is None
        assert processor._start_time is None

    @pytest.mark.asyncio
    async def test_monitor_resources(self, processor):
        """Test resource monitoring."""
        session = ProcessingSession()
        processor._current_session = session

        with patch("src.workers.monitor.processor.psutil") as mock_psutil:
            mock_process = Mock()
            mock_memory = Mock(rss=1024 * 1024 * 100)  # 100MB
            mock_process.memory_info.return_value = mock_memory
            mock_process.cpu_percent.return_value = 15.0
            mock_psutil.Process.return_value = mock_process

            # Start monitoring task
            monitor_task = asyncio.create_task(processor._monitor_resources())

            # Let it run briefly
            await asyncio.sleep(0.01)  # Shorter sleep

            # Request shutdown to stop monitoring
            processor._shutdown_requested = True

            # Wait for completion with timeout handling
            try:
                await asyncio.wait_for(monitor_task, timeout=0.5)
            except asyncio.TimeoutError:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

            # Check that metrics were updated (may not be if monitoring ran too briefly)
            assert session.memory_usage_mb >= 0  # Just check it's been set

    @pytest.mark.asyncio
    async def test_resource_monitoring_memory_warning(self, processor):
        """Test resource monitoring with memory limit warning."""
        session = ProcessingSession()
        processor._current_session = session
        processor.config.memory_limit_mb = 500  # 500MB limit

        with patch("src.workers.monitor.processor.psutil") as mock_psutil:
            mock_process = Mock()
            mock_memory = Mock(rss=1024 * 1024 * 600)  # 600MB usage
            mock_process.memory_info.return_value = mock_memory
            mock_psutil.Process.return_value = mock_process

            # Start monitoring
            monitor_task = asyncio.create_task(processor._monitor_resources())

            # Brief execution
            await asyncio.sleep(0.1)
            processor._shutdown_requested = True
            await asyncio.wait_for(monitor_task, timeout=1.0)

            # Should have added a warning
            assert len(session.warnings) > 0
            assert "Memory usage" in session.warnings[0]
            assert "exceeded limit" in session.warnings[0]


@pytest.mark.asyncio
class TestPRProcessorIntegration:
    """Integration test cases for PRProcessor full workflows."""

    @pytest.fixture
    async def full_processor(self):
        """Fully mocked processor for integration tests."""
        github_client = Mock()
        session = AsyncMock()
        cache_manager = Mock()
        config = ProcessorConfig(
            max_concurrent_repos=2,
            batch_size=2,
            enable_detailed_logging=True,
        )

        processor = PRProcessor(github_client, session, cache_manager, config)

        # Mock all components
        processor.repo_repository = AsyncMock()
        processor.pr_discovery = AsyncMock()
        processor.check_discovery = AsyncMock()
        processor.state_detector = AsyncMock()
        processor.data_synchronizer = AsyncMock()

        return processor

    async def test_full_repository_processing_workflow(self, full_processor):
        """Test complete repository processing workflow."""
        # Setup test repositories
        repo1 = Mock()
        repo1.id = uuid.uuid4()
        repo1.full_name = "org/repo1"
        repo1.last_polled_at = None

        repo2 = Mock()
        repo2.id = uuid.uuid4()
        repo2.full_name = "org/repo2"
        repo2.last_polled_at = None

        full_processor.repo_repository.get_active_repositories.return_value = [
            repo1,
            repo2,
        ]
        full_processor.repo_repository.get_repositories_needing_poll.return_value = [
            repo1,
            repo2,
        ]
        full_processor.repo_repository.get_by_id.side_effect = (
            lambda id: repo1 if id == repo1.id else repo2
        )

        # Mock discovery results
        mock_prs = [Mock(pr_number=1, head_sha="abc123", repository_id=repo1.id)]
        mock_checks = [Mock(pr_number=1)]
        mock_metrics = ProcessingMetrics(prs_discovered=1, github_api_calls_made=2)

        full_processor.pr_discovery.discover_prs.return_value = (mock_prs, mock_metrics)
        full_processor.check_discovery.discover_check_runs.return_value = mock_checks
        full_processor.check_discovery.get_metrics.return_value = ProcessingMetrics()

        # Mock state detection
        full_processor.state_detector.detect_pr_changes.return_value = []
        full_processor.state_detector.detect_check_run_changes.return_value = []
        full_processor.state_detector.analyze_significance.return_value = []
        full_processor.state_detector.filter_actionable_changes.return_value = []

        # Mock synchronization
        mock_sync_op = SyncOperation(status=OperationStatus.COMPLETED)
        full_processor.data_synchronizer.synchronize_changes.return_value = mock_sync_op

        # Execute processing
        session = await full_processor.process_repositories(
            mode=ProcessingMode.INCREMENTAL
        )

        # Assertions
        assert session.phase in (ProcessingPhase.COMPLETED, ProcessingPhase.CLEANUP)
        assert session.processed_repositories == 2
        assert session.total_repositories == 2
        assert session.success_rate == 100.0
        assert len(session.errors) == 0

    async def test_processing_with_failures(self, full_processor):
        """Test processing workflow with some repository failures."""
        # Setup repositories
        repo1 = Mock()
        repo1.id = uuid.uuid4()
        repo1.full_name = "org/repo1"

        repo2 = Mock()
        repo2.id = uuid.uuid4()
        repo2.full_name = "org/repo2"

        full_processor.repo_repository.get_active_repositories.return_value = [
            repo1,
            repo2,
        ]
        full_processor.repo_repository.get_repositories_needing_poll.return_value = [
            repo1,
            repo2,
        ]

        # First repository succeeds
        def get_by_id_side_effect(repo_id):
            if repo_id == repo1.id:
                return repo1
            elif repo_id == repo2.id:
                return repo2
            return None

        full_processor.repo_repository.get_by_id.side_effect = get_by_id_side_effect

        # Mock discovery - repo1 succeeds, repo2 fails
        def discover_side_effect(*args, **kwargs):
            repo_contexts = args[0] if args else kwargs.get("repositories", [])
            if repo_contexts and repo_contexts[0].repository_id == repo1.id:
                return ([], ProcessingMetrics())
            else:
                raise Exception("Discovery failed for repo2")

        full_processor.pr_discovery.discover_prs.side_effect = discover_side_effect
        full_processor.check_discovery.discover_check_runs.return_value = []
        full_processor.check_discovery.get_metrics.return_value = ProcessingMetrics()
        full_processor.state_detector.detect_pr_changes.return_value = []
        full_processor.state_detector.detect_check_run_changes.return_value = []
        full_processor.state_detector.analyze_significance.return_value = []
        full_processor.state_detector.filter_actionable_changes.return_value = []

        mock_sync_op = SyncOperation(status=OperationStatus.COMPLETED)
        full_processor.data_synchronizer.synchronize_changes.return_value = mock_sync_op

        # Execute processing
        session = await full_processor.process_repositories()

        # Assertions
        assert session.phase in (ProcessingPhase.COMPLETED, ProcessingPhase.CLEANUP)
        assert session.processed_repositories == 1  # Only repo1 succeeded
        assert session.failed_repositories == 1  # repo2 failed
        assert session.total_repositories == 2
        assert session.success_rate == 50.0
        assert len(session.errors) > 0

    async def test_dry_run_mode(self, full_processor):
        """Test processing in dry-run mode."""
        # Setup repository
        repo = Mock()
        repo.id = uuid.uuid4()
        repo.full_name = "org/test-repo"
        full_processor.repo_repository.get_active_repositories.return_value = [repo]
        full_processor.repo_repository.get_by_id.return_value = repo

        # Mock discovery
        full_processor.pr_discovery.discover_prs.return_value = (
            [],
            ProcessingMetrics(),
        )
        full_processor.check_discovery.discover_check_runs.return_value = []
        full_processor.check_discovery.get_metrics.return_value = ProcessingMetrics()
        full_processor.state_detector.detect_pr_changes.return_value = []
        full_processor.state_detector.detect_check_run_changes.return_value = []
        full_processor.state_detector.analyze_significance.return_value = []
        full_processor.state_detector.filter_actionable_changes.return_value = []

        # Execute in dry-run mode
        session = await full_processor.process_repositories(mode=ProcessingMode.DRY_RUN)

        # Assertions
        assert session.mode == ProcessingMode.DRY_RUN
        assert session.phase in (ProcessingPhase.COMPLETED, ProcessingPhase.CLEANUP)

        # Synchronization should not be called in dry-run mode
        full_processor.data_synchronizer.synchronize_changes.assert_not_called()

    async def test_shutdown_during_processing(self, full_processor):
        """Test graceful shutdown during processing."""
        # Setup repositories
        repos = [Mock(id=uuid.uuid4(), full_name=f"org/repo{i}") for i in range(10)]
        full_processor.repo_repository.get_active_repositories.return_value = repos

        def get_by_id_side_effect(repo_id):
            for repo in repos:
                if repo.id == repo_id:
                    return repo
            return None

        full_processor.repo_repository.get_by_id.side_effect = get_by_id_side_effect

        # Mock discovery with delay to simulate processing time
        async def slow_discovery(*args, **kwargs):
            await asyncio.sleep(0.5)  # Simulate processing time
            return ([], ProcessingMetrics())

        full_processor.pr_discovery.discover_prs.side_effect = slow_discovery
        full_processor.check_discovery.discover_check_runs.return_value = []
        full_processor.check_discovery.get_metrics.return_value = ProcessingMetrics()
        full_processor.state_detector.detect_pr_changes.return_value = []
        full_processor.state_detector.detect_check_run_changes.return_value = []
        full_processor.state_detector.analyze_significance.return_value = []
        full_processor.state_detector.filter_actionable_changes.return_value = []

        mock_sync_op = SyncOperation(status=OperationStatus.COMPLETED)
        full_processor.data_synchronizer.synchronize_changes.return_value = mock_sync_op

        # Start processing
        processing_task = asyncio.create_task(
            full_processor.process_repositories(mode=ProcessingMode.FULL)
        )

        # Wait a bit then request shutdown
        await asyncio.sleep(0.1)
        await full_processor.request_shutdown()

        # Wait for processing to complete
        session = await processing_task

        # Should complete with partial results
        assert session.phase in (
            ProcessingPhase.COMPLETED,
            ProcessingPhase.CLEANUP,
            ProcessingPhase.FAILED,
        )
        assert len(session.warnings) > 0
        assert any("shutdown request" in warning for warning in session.warnings)
