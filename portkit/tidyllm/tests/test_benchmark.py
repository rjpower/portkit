"""Tests for benchmark framework."""

from unittest.mock import Mock

import pytest

from portkit.tidyllm import FunctionLibrary
from portkit.tidyllm.benchmark import (
    BenchmarkContext,
    BenchmarkResult,
    BenchmarkRunner,
    benchmark_test,
    run_benchmarks,
)
from portkit.tidyllm.llm import LLMHelper, LLMResponse, MockLLMClient
from portkit.tidyllm.tools.calculator import calculator


class TestBenchmarkDecorator:
    """Test the @benchmark_test decorator."""

    def test_decorator_marks_function(self):
        """Test that decorator properly marks functions."""

        @benchmark_test()
        def test_func():
            pass

        assert hasattr(test_func, "__benchmark_test__")
        assert test_func.__benchmark_test__ is True
        assert test_func.__benchmark_timeout__ == 30

    def test_decorator_with_custom_timeout(self):
        """Test decorator with custom timeout."""

        @benchmark_test(timeout_seconds=60)
        def test_func():
            pass

        assert test_func.__benchmark_timeout__ == 60


class TestBenchmarkContext:
    """Test benchmark context and assertions."""

    def setup_method(self):
        """Set up test context."""
        library = FunctionLibrary(functions=[calculator])
        client = MockLLMClient()
        llm = LLMHelper("mock-model", library, client)
        self.context = BenchmarkContext(llm)

    def test_assert_tool_called_success(self):
        """Test successful tool assertion."""
        response = LLMResponse(success=True, tool_called="calculator", tool_result=Mock())

        self.context.assert_tool_called(response, "calculator")
        assert self.context._assertions_passed == 1
        assert self.context._assertions_total == 1

    def test_assert_tool_called_failure(self):
        """Test failed tool assertion."""
        response = LLMResponse(success=True, tool_called="wrong_tool", tool_result=Mock())

        with pytest.raises(AssertionError, match="Expected tool 'calculator'"):
            self.context.assert_tool_called(response, "calculator")

        assert self.context._assertions_passed == 0
        assert self.context._assertions_total == 1

    def test_assert_success(self):
        """Test success assertion."""
        response = LLMResponse(success=True)
        self.context.assert_success(response)

        assert self.context._assertions_passed == 1

        response_fail = LLMResponse(success=False, error_message="Test error")
        with pytest.raises(AssertionError, match="LLM response failed"):
            self.context.assert_success(response_fail)

    def test_assert_result_contains(self):
        """Test result contains assertion."""
        response = LLMResponse(success=True, tool_result="Hello World")

        self.context.assert_result_contains(response, "World")
        assert self.context._assertions_passed == 1

        with pytest.raises(AssertionError, match="Expected 'Missing'"):
            self.context.assert_result_contains(response, "Missing")

    def test_assert_result_equals(self):
        """Test result equals assertion."""
        response = LLMResponse(success=True, tool_result=42)

        self.context.assert_result_equals(response, 42)
        assert self.context._assertions_passed == 1

        with pytest.raises(AssertionError, match="Expected 100"):
            self.context.assert_result_equals(response, 100)


class TestBenchmarkRunner:
    """Test benchmark runner functionality."""

    def setup_method(self):
        """Set up test runner."""
        library = FunctionLibrary(functions=[calculator])
        self.runner = BenchmarkRunner(library)

    def test_discover_tests(self):
        """Test test discovery from modules."""
        # Create a mock module with benchmark tests
        mock_module = Mock()

        @benchmark_test()
        def test_func1():
            pass

        def regular_func():
            pass

        @benchmark_test()
        def test_func2():
            pass

        mock_module.__dict__ = {
            "test_func1": test_func1,
            "regular_func": regular_func,
            "test_func2": test_func2,
            "other_attr": "not a function",
        }

        # Mock dir() to return the keys
        import builtins

        original_dir = builtins.dir
        builtins.dir = lambda x: list(x.__dict__.keys())

        try:
            tests = self.runner.discover_tests([mock_module])
            assert len(tests) == 2
            assert test_func1 in tests
            assert test_func2 in tests
            assert regular_func not in tests
        finally:
            builtins.dir = original_dir

    def test_run_test_success(self):
        """Test successful test execution."""

        @benchmark_test()
        def test_success(context):
            # This should succeed with mock client
            pass

        result = self.runner.run_test(test_success, "mock", use_mock=True)

        assert isinstance(result, BenchmarkResult)
        assert result.success is True
        assert result.test_name == "test_success"
        assert result.duration_ms >= 0
        assert result.error_message is None

    def test_run_test_failure(self):
        """Test failed test execution."""

        @benchmark_test()
        def test_failure():
            raise ValueError("Test error")

        result = self.runner.run_test(test_failure, "mock", use_mock=True)

        assert isinstance(result, BenchmarkResult)
        assert result.success is False
        assert result.test_name == "test_failure"
        assert result.error_message and "Test error" in result.error_message

    def test_run_test_with_context(self):
        """Test running test that expects context parameter."""

        @benchmark_test()
        def test_with_context(context):
            assert context is not None
            assert hasattr(context, "llm")

        result = self.runner.run_test(test_with_context, "mock", use_mock=True)
        assert result.success is True

    def test_run_test_without_context(self):
        """Test running test that doesn't expect context."""

        @benchmark_test()
        def test_without_context():
            # Just a simple test without context parameter
            assert True

        result = self.runner.run_test(test_without_context, "mock", use_mock=True)
        assert result.success is True

    def test_run_tests_multiple(self):
        """Test running multiple tests."""

        @benchmark_test()
        def test1():
            pass

        @benchmark_test()
        def test2():
            pass

        @benchmark_test()
        def test_fail():
            raise RuntimeError("Intentional failure")

        results = self.runner.run_tests([test1, test2, test_fail], "mock", use_mock=True)

        assert isinstance(results, list)
        assert len(results) == 3
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        assert passed == 2
        assert failed == 1


class TestBenchmarkIntegration:
    """Integration tests for the full benchmark system."""

    def test_run_benchmarks_with_modules(self):
        """Test running benchmarks with provided modules."""
        library = FunctionLibrary(functions=[calculator])

        # Create mock module with tests
        mock_module = Mock()

        @benchmark_test()
        def integration_test():
            assert True

        mock_module.__dict__ = {"integration_test": integration_test}

        # Mock dir() for test discovery
        import builtins

        original_dir = builtins.dir
        builtins.dir = lambda x: list(x.__dict__.keys())

        try:
            results = run_benchmarks(
                function_library=library,
                model="mock",
                test_modules=[mock_module],
                mock_client=True,
            )

            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0].success is True
        finally:
            builtins.dir = original_dir

    def test_run_benchmarks_no_tests(self):
        """Test running benchmarks when no tests are found."""
        library = FunctionLibrary(functions=[calculator])
        mock_module = Mock()
        mock_module.__dict__ = {}

        import builtins

        original_dir = builtins.dir
        builtins.dir = lambda x: list(x.__dict__.keys())

        try:
            results = run_benchmarks(
                function_library=library,
                model="mock",
                test_modules=[mock_module],
                mock_client=True,
            )

            assert len(results) == 0
        finally:
            builtins.dir = original_dir

    def test_run_benchmarks_no_tests_found(self):
        """Test when no tests are found."""
        library = FunctionLibrary(functions=[calculator])

        results = run_benchmarks(function_library=library, model="mock", mock_client=True)

        assert len(results) == 0
