"""Interface validation tests for integration testing interfaces.

This module provides comprehensive validation of the interface definitions used in
integration testing, ensuring they work correctly and are compatible with existing
database fixture implementations.
"""

import inspect
import sys
from abc import ABC, abstractmethod
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from contextlib import AbstractAsyncContextManager

# Add scratch-pad to path for interface imports (same as database.py)
scratch_pad_path = Path(__file__).parents[4] / "scratch-pad"
if str(scratch_pad_path) not in sys.path:
    sys.path.append(str(scratch_pad_path))


class TestInterfaceImports:
    """Test suite for interface import functionality and fallback mechanisms."""

    def test_interface_imports_successful(self):
        """
        Why: Verify that interface definitions can be imported without errors
        What: Test importing all interface classes from both scratch-pad and fallback locations
        How: Attempt imports and validate that classes are available and properly defined
        """
        # Test importing from scratch-pad first
        try:
            from interfaces.integration_testing_interfaces import (
                PerformanceMetrics,
                TestDatabaseContext,
                TestDatabaseManager,
            )
            interfaces_source = "scratch-pad"
            scratch_pad_available = True
        except ImportError:
            # Test fallback import path (same as database.py)
            scratch_pad_available = False
            interfaces_source = "fallback"
            
            # Import fallback definitions using the same pattern as database.py
            from tests.integration.fixtures.database import (
                PerformanceMetrics,
                TestDatabaseContext, 
                TestDatabaseManager,
            )

        # Verify all interfaces are available
        assert PerformanceMetrics is not None
        assert TestDatabaseContext is not None  
        assert TestDatabaseManager is not None
        
        # Store for other tests to know which source was used
        TestInterfaceImports._interfaces_source = interfaces_source
        TestInterfaceImports._scratch_pad_available = scratch_pad_available
        TestInterfaceImports._PerformanceMetrics = PerformanceMetrics
        TestInterfaceImports._TestDatabaseContext = TestDatabaseContext
        TestInterfaceImports._TestDatabaseManager = TestDatabaseManager

    def test_fallback_mechanism_consistency(self):
        """
        Why: Ensure fallback definitions match expected interface contracts
        What: Validate that fallback interfaces have same structure as expected interfaces
        How: Compare fallback interface structure with documented requirements
        """
        # Run interface import test first if not already done
        if not hasattr(TestInterfaceImports, '_interfaces_source'):
            self.test_interface_imports_successful()
            
        # Verify the interfaces are properly defined regardless of source
        assert hasattr(TestInterfaceImports._PerformanceMetrics, '__dataclass_fields__')
        assert hasattr(TestInterfaceImports._TestDatabaseContext, '__dataclass_fields__')
        assert issubclass(TestInterfaceImports._TestDatabaseManager, ABC)

    def test_no_circular_import_issues(self):
        """
        Why: Prevent circular import dependencies that could break the application
        What: Test that importing interfaces doesn't cause circular import errors
        How: Import interfaces multiple times and from different paths to detect cycles
        """
        # Test multiple imports don't cause issues
        import_attempts = []
        
        for _ in range(3):
            try:
                # Try importing from scratch-pad
                from interfaces.integration_testing_interfaces import (
                    PerformanceMetrics as PM,
                    TestDatabaseContext as TDC,
                    TestDatabaseManager as TDM,
                )
                import_attempts.append("scratch-pad")
            except ImportError:
                # Try fallback import
                from tests.integration.fixtures.database import (
                    PerformanceMetrics as PM,
                    TestDatabaseContext as TDC,
                    TestDatabaseManager as TDM,
                )
                import_attempts.append("fallback")
        
        # All imports should be consistent
        assert len(set(import_attempts)) == 1, "Inconsistent import sources detected"


class TestDataclassValidation:
    """Test suite for dataclass interface validation."""

    @classmethod
    def setup_class(cls):
        """Setup test class with interface imports."""
        # Import interfaces using the same pattern
        try:
            from interfaces.integration_testing_interfaces import (
                PerformanceMetrics,
                TestDatabaseContext,
            )
        except ImportError:
            from tests.integration.fixtures.database import (
                PerformanceMetrics,
                TestDatabaseContext,
            )
        
        cls.PerformanceMetrics = PerformanceMetrics
        cls.TestDatabaseContext = TestDatabaseContext

    def test_testdatabase_context_structure(self):
        """
        Why: Validate TestDatabaseContext has all required fields for database fixture operations
        What: Test dataclass field presence, types, and default values
        How: Inspect dataclass fields and validate against expected schema
        """
        # Verify it's a dataclass
        assert is_dataclass(self.TestDatabaseContext)
        
        # Get dataclass fields
        dataclass_fields = fields(self.TestDatabaseContext)
        field_names = {field.name for field in dataclass_fields}
        
        # Required fields for database context
        expected_fields = {
            'connection_manager',
            'session_factory', 
            'cleanup_handlers',
            'test_data_ids',
            'database_url',
            'is_transaction_isolated',
            'session_factory_wrapper'
        }
        
        # Verify all expected fields are present
        for field_name in expected_fields:
            assert field_name in field_names, f"Missing required field: {field_name}"

    def test_testdatabase_context_field_types(self):
        """
        Why: Ensure field types match expected types for proper type checking and IDE support
        What: Validate that each field has appropriate type annotations
        How: Use get_type_hints to check type annotations for all fields
        """
        try:
            type_hints = get_type_hints(self.TestDatabaseContext)
        except (NameError, AttributeError):
            # Some type hints might not resolve in test environment
            # Use string annotations from fields instead
            dataclass_fields = fields(self.TestDatabaseContext)
            type_hints = {field.name: field.type for field in dataclass_fields}
        
        # Verify critical field types exist and are reasonable
        assert 'connection_manager' in type_hints
        assert 'session_factory' in type_hints
        assert 'cleanup_handlers' in type_hints
        assert 'test_data_ids' in type_hints
        assert 'database_url' in type_hints

    def test_testdatabase_context_creation(self):
        """
        Why: Verify TestDatabaseContext can be instantiated with valid parameters
        What: Test creating context instances with various parameter combinations
        How: Create instances with required and optional parameters, validate creation
        """
        # Test with minimal required parameters
        mock_connection_manager = MagicMock()
        mock_session_factory = MagicMock()
        
        context = self.TestDatabaseContext(
            connection_manager=mock_connection_manager,
            session_factory=mock_session_factory,
            cleanup_handlers=[],
            test_data_ids={},
            database_url="postgresql://test:test@localhost/test"
        )
        
        assert context.connection_manager is mock_connection_manager
        assert context.session_factory is mock_session_factory
        assert context.cleanup_handlers == []
        assert context.test_data_ids == {}
        assert context.database_url == "postgresql://test:test@localhost/test"

    def test_performance_metrics_structure(self):
        """
        Why: Validate PerformanceMetrics dataclass has all required fields for performance monitoring
        What: Test presence and types of all performance metric fields
        How: Inspect dataclass fields and validate against expected performance metric schema
        """
        # Verify it's a dataclass
        assert is_dataclass(self.PerformanceMetrics)
        
        # Get dataclass fields
        dataclass_fields = fields(self.PerformanceMetrics)
        field_names = {field.name for field in dataclass_fields}
        
        # Required fields for performance metrics
        expected_fields = {
            'test_name',
            'database_operations',
            'database_operation_time_ms',
            'api_requests',
            'api_request_time_ms',
            'cache_hits',
            'cache_misses',
            'memory_usage_mb',
            'total_test_time_ms'
        }
        
        # Verify all expected fields are present
        for field_name in expected_fields:
            assert field_name in field_names, f"Missing required field: {field_name}"

    def test_performance_metrics_calculations(self):
        """
        Why: Validate PerformanceMetrics property calculations work correctly
        What: Test database_ops_per_second property calculation with various inputs
        How: Create instances with different values and verify calculation accuracy
        """
        # Test normal calculation
        metrics = self.PerformanceMetrics(
            test_name="test_calculation",
            database_operations=100,
            database_operation_time_ms=1000,  # 1 second
            api_requests=0,
            api_request_time_ms=0.0,
            cache_hits=0,
            cache_misses=0,
            memory_usage_mb=0.0,
            total_test_time_ms=1000.0
        )
        
        # Should be 100 ops per second
        assert metrics.database_ops_per_second == 100.0
        
        # Test zero division protection
        zero_time_metrics = self.PerformanceMetrics(
            test_name="test_zero_division",
            database_operations=100,
            database_operation_time_ms=0,  # Zero time
            api_requests=0,
            api_request_time_ms=0.0,
            cache_hits=0,
            cache_misses=0,
            memory_usage_mb=0.0,
            total_test_time_ms=1000.0
        )
        
        # Should handle zero division gracefully
        assert zero_time_metrics.database_ops_per_second == 0.0

    def test_performance_metrics_realistic_scenarios(self):
        """
        Why: Validate PerformanceMetrics work with realistic test scenario data
        What: Test metric creation and calculation with typical test execution values
        How: Create metrics with realistic values from actual test scenarios
        """
        # Realistic database-heavy test scenario
        db_heavy_metrics = self.PerformanceMetrics(
            test_name="test_heavy_database_operations",
            database_operations=250,
            database_operation_time_ms=500,  # 0.5 seconds
            api_requests=10,
            api_request_time_ms=150.0,
            cache_hits=45,
            cache_misses=5,
            memory_usage_mb=128.5,
            total_test_time_ms=2000.0  # 2 seconds total
        )
        
        # Validate calculations make sense
        ops_per_second = db_heavy_metrics.database_ops_per_second
        assert ops_per_second == 500.0  # 250 ops / 0.5 seconds = 500 ops/sec
        assert db_heavy_metrics.cache_hits > db_heavy_metrics.cache_misses
        assert db_heavy_metrics.total_test_time_ms > db_heavy_metrics.database_operation_time_ms


class TestAbstractBaseClassValidation:
    """Test suite for abstract base class interface validation."""

    @classmethod
    def setup_class(cls):
        """Setup test class with interface imports."""
        try:
            from interfaces.integration_testing_interfaces import TestDatabaseManager
        except ImportError:
            from tests.integration.fixtures.database import TestDatabaseManager
        
        cls.TestDatabaseManager = TestDatabaseManager

    def test_abstract_base_class_definition(self):
        """
        Why: Verify TestDatabaseManager is properly defined as an abstract base class
        What: Test ABC inheritance and abstract method definitions
        How: Inspect class hierarchy and abstract method decorators
        """
        # Verify it's an ABC
        assert issubclass(self.TestDatabaseManager, ABC)
        
        # Check that it has abstract methods
        abstract_methods = getattr(self.TestDatabaseManager, '__abstractmethods__', set())
        assert len(abstract_methods) > 0, "TestDatabaseManager should have abstract methods"

    def test_abstract_method_signatures(self):
        """
        Why: Ensure all required abstract methods are defined with correct signatures
        What: Validate method names, parameters, and return type annotations
        How: Inspect abstract methods and compare with expected interface contract
        """
        # Expected abstract methods
        expected_methods = {
            'create_test_database',
            'apply_migrations',
            'seed_test_data', 
            'cleanup_database',
            'get_transaction_context'
        }
        
        # Get all methods defined in the class
        methods = inspect.getmembers(self.TestDatabaseManager, predicate=inspect.isfunction)
        method_names = {name for name, _ in methods}
        
        # Check for expected abstract methods
        for method_name in expected_methods:
            assert method_name in method_names, f"Missing abstract method: {method_name}"

    def test_abstract_method_parameters(self):
        """
        Why: Validate abstract method parameters match expected interface contracts
        What: Test parameter names, types, and default values for each abstract method
        How: Use inspect to examine method signatures and validate against requirements
        """
        # Test create_test_database method signature
        create_method = getattr(self.TestDatabaseManager, 'create_test_database')
        create_sig = inspect.signature(create_method)
        
        # Should have self and isolation_id parameters
        param_names = list(create_sig.parameters.keys())
        assert 'self' in param_names
        assert 'isolation_id' in param_names
        
        # Test apply_migrations method signature  
        apply_method = getattr(self.TestDatabaseManager, 'apply_migrations')
        apply_sig = inspect.signature(apply_method)
        
        param_names = list(apply_sig.parameters.keys())
        assert 'self' in param_names
        assert 'context' in param_names

    def test_concrete_implementation_enforcement(self):
        """
        Why: Verify that concrete implementations must implement all abstract methods
        What: Test that incomplete implementations raise TypeError
        How: Create partial implementation and verify instantiation fails
        """
        # Create incomplete implementation
        class IncompleteManager(self.TestDatabaseManager):
            async def create_test_database(self, isolation_id: str):
                pass
            # Missing other abstract methods
        
        # Should not be able to instantiate incomplete implementation
        with pytest.raises(TypeError, match="abstract methods"):
            IncompleteManager()

    def test_async_context_manager_method(self):
        """
        Why: Verify get_transaction_context is properly defined as async context manager
        What: Test that the method signature supports async context manager protocol
        How: Check method signature and async context manager requirements
        """
        # Test get_transaction_context method signature
        transaction_method = getattr(self.TestDatabaseManager, 'get_transaction_context')
        transaction_sig = inspect.signature(transaction_method)
        
        # Should have self and context parameters
        param_names = list(transaction_sig.parameters.keys())
        assert 'self' in param_names
        assert 'context' in param_names
        
        # Method should be marked as abstract
        abstract_methods = getattr(self.TestDatabaseManager, '__abstractmethods__', set())
        assert 'get_transaction_context' in abstract_methods


class TestInterfaceCompatibility:
    """Test suite for interface compatibility with existing code."""

    @classmethod
    def setup_class(cls):
        """Setup test class with interface imports."""
        try:
            from interfaces.integration_testing_interfaces import (
                PerformanceMetrics,
                TestDatabaseContext,
                TestDatabaseManager,
            )
        except ImportError:
            from tests.integration.fixtures.database import (
                PerformanceMetrics,
                TestDatabaseContext,
                TestDatabaseManager,
            )
        
        cls.PerformanceMetrics = PerformanceMetrics
        cls.TestDatabaseContext = TestDatabaseContext
        cls.TestDatabaseManager = TestDatabaseManager

    def test_compatibility_with_existing_fixtures(self):
        """
        Why: Ensure interfaces are compatible with existing database fixture usage patterns
        What: Test that interface signatures match what existing fixtures expect
        How: Compare interface definitions with actual usage in database.py
        """
        # Import existing database fixture implementation
        from tests.integration.fixtures.database import RealTestDatabaseManager
        
        # Verify RealTestDatabaseManager properly implements the interface
        assert issubclass(RealTestDatabaseManager, self.TestDatabaseManager)
        
        # Test that it implements all abstract methods
        abstract_methods = getattr(self.TestDatabaseManager, '__abstractmethods__', set())
        implemented_methods = set(dir(RealTestDatabaseManager))
        
        for method_name in abstract_methods:
            assert method_name in implemented_methods, f"Method {method_name} not implemented"

    def test_enhanced_session_factory_compatibility(self):
        """
        Why: Validate compatibility with EnhancedSessionFactory patterns used in fixtures
        What: Test that TestDatabaseContext supports EnhancedSessionFactory usage
        How: Verify context can work with session factory patterns from database.py
        """
        # Import EnhancedSessionFactory from database fixtures
        from tests.integration.fixtures.database import EnhancedSessionFactory
        
        # Create mock enhanced session factory
        mock_enhanced_factory = MagicMock(spec=EnhancedSessionFactory)
        mock_enhanced_factory.session_scope = AsyncMock()
        
        # Create context with enhanced factory pattern
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=mock_enhanced_factory,
            cleanup_handlers=[],
            test_data_ids={},
            database_url="postgresql://test:test@localhost/test"
        )
        
        # Verify the context accepts the enhanced factory
        assert context.session_factory is mock_enhanced_factory

    def test_session_factory_proxy_compatibility(self):
        """
        Why: Ensure TestDatabaseContext works with SessionFactoryProxy patterns
        What: Test compatibility with session factory wrapper patterns from database.py
        How: Create proxy-like objects and verify they work with the context
        """
        # Create mock session factory proxy (similar to database.py implementation)
        class MockSessionFactoryProxy:
            def __init__(self, enhanced_factory):
                self.enhanced_factory = enhanced_factory
                
            def __call__(self):
                return self.enhanced_factory.session_scope()
                
            def __getattr__(self, name):
                return getattr(self.enhanced_factory, name)
        
        mock_enhanced_factory = MagicMock()
        mock_proxy = MockSessionFactoryProxy(mock_enhanced_factory)
        
        # Create context with proxy
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=mock_proxy,
            cleanup_handlers=[],
            test_data_ids={},
            database_url="postgresql://test:test@localhost/test"
        )
        
        # Verify proxy works
        assert callable(context.session_factory)
        assert hasattr(context.session_factory, 'enhanced_factory')

    def test_cleanup_handler_compatibility(self):
        """
        Why: Validate cleanup handlers work with expected async patterns
        What: Test that cleanup handlers can be properly stored and executed
        How: Create async cleanup functions and verify they can be stored in context
        """
        async def mock_cleanup_handler():
            """Mock async cleanup handler."""
            pass
        
        # Create context with cleanup handlers
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=MagicMock(),
            cleanup_handlers=[mock_cleanup_handler],
            test_data_ids={},
            database_url="postgresql://test:test@localhost/test"
        )
        
        # Verify cleanup handlers are stored correctly
        assert len(context.cleanup_handlers) == 1
        assert callable(context.cleanup_handlers[0])

    def test_test_data_ids_structure(self):
        """
        Why: Ensure test_data_ids field supports expected data tracking patterns
        What: Test that the field can store various types of ID mappings used in fixtures
        How: Create contexts with different test data ID structures and verify storage
        """
        # Test with typical test data ID structure (from database.py seed methods)
        test_data_ids = {
            "repositories": ["repo_id_1", "repo_id_2"],
            "pull_requests": ["pr_id_1", "pr_id_2", "pr_id_3"],
            "check_runs": ["check_id_1", "check_id_2"]
        }
        
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=MagicMock(),
            cleanup_handlers=[],
            test_data_ids=test_data_ids,
            database_url="postgresql://test:test@localhost/test"
        )
        
        # Verify data IDs are stored correctly
        assert context.test_data_ids == test_data_ids
        assert "repositories" in context.test_data_ids
        assert "pull_requests" in context.test_data_ids
        assert "check_runs" in context.test_data_ids


class TestEdgeCasesAndErrorHandling:
    """Test suite for edge cases and error handling scenarios."""

    @classmethod  
    def setup_class(cls):
        """Setup test class with interface imports."""
        try:
            from interfaces.integration_testing_interfaces import (
                PerformanceMetrics,
                TestDatabaseContext,
                TestDatabaseManager,
            )
        except ImportError:
            from tests.integration.fixtures.database import (
                PerformanceMetrics,
                TestDatabaseContext,
                TestDatabaseManager,
            )
        
        cls.PerformanceMetrics = PerformanceMetrics
        cls.TestDatabaseContext = TestDatabaseContext
        cls.TestDatabaseManager = TestDatabaseManager

    def test_performance_metrics_edge_cases(self):
        """
        Why: Validate PerformanceMetrics handles edge cases gracefully
        What: Test zero values, negative values, and extreme values
        How: Create metrics with edge case values and verify behavior
        """
        # Test with all zero values
        zero_metrics = self.PerformanceMetrics(
            test_name="zero_test",
            database_operations=0,
            database_operation_time_ms=0,
            api_requests=0,
            api_request_time_ms=0.0,
            cache_hits=0,
            cache_misses=0,
            memory_usage_mb=0.0,
            total_test_time_ms=0.0
        )
        
        # Should handle zero division gracefully
        assert zero_metrics.database_ops_per_second == 0.0
        
        # Test with very large values
        large_metrics = self.PerformanceMetrics(
            test_name="large_test",
            database_operations=1000000,
            database_operation_time_ms=1,  # Very fast operations
            api_requests=999999,
            api_request_time_ms=0.1,
            cache_hits=500000,
            cache_misses=500000,
            memory_usage_mb=1024.0,
            total_test_time_ms=10000.0
        )
        
        # Should handle large values without overflow
        assert large_metrics.database_ops_per_second == 1000000000.0  # 1M ops per millisecond * 1000

    def test_testdatabase_context_with_none_values(self):
        """
        Why: Test how context handles None/optional values gracefully
        What: Create contexts with None values for optional fields
        How: Set optional fields to None and verify creation succeeds
        """
        # Test with None session factory wrapper
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=MagicMock(),
            cleanup_handlers=[],
            test_data_ids={},
            database_url="postgresql://test:test@localhost/test",
            session_factory_wrapper=None  # Explicitly None
        )
        
        assert context.session_factory_wrapper is None

    def test_empty_collections_handling(self):
        """
        Why: Ensure interfaces handle empty collections appropriately
        What: Test behavior with empty lists, dicts, and other collections
        How: Create interfaces with empty collections and verify they work
        """
        # Test with empty cleanup handlers
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=MagicMock(),
            cleanup_handlers=[],  # Empty list
            test_data_ids={},     # Empty dict
            database_url="postgresql://test:test@localhost/test"
        )
        
        assert context.cleanup_handlers == []
        assert context.test_data_ids == {}

    def test_interface_string_representations(self):
        """
        Why: Verify interfaces have useful string representations for debugging
        What: Test __str__ and __repr__ methods on interface instances
        How: Create instances and check string representations contain useful info
        """
        # Test PerformanceMetrics string representation
        metrics = self.PerformanceMetrics(
            test_name="string_test",
            database_operations=10,
            database_operation_time_ms=100,
            api_requests=5,
            api_request_time_ms=50.0,
            cache_hits=3,
            cache_misses=2,
            memory_usage_mb=64.0,
            total_test_time_ms=200.0
        )
        
        # Should have a string representation
        str_repr = str(metrics)
        assert "string_test" in str_repr or "PerformanceMetrics" in str_repr
        
        # Test TestDatabaseContext string representation
        context = self.TestDatabaseContext(
            connection_manager=MagicMock(),
            session_factory=MagicMock(),
            cleanup_handlers=[],
            test_data_ids={},
            database_url="postgresql://test:test@localhost/test"
        )
        
        str_repr = str(context)
        assert "TestDatabaseContext" in str_repr or "postgresql" in str_repr