"""Tests for evaluation framework."""

from unittest.mock import Mock

import pytest

from portkit.tidyllm import FunctionLibrary
from portkit.tidyllm.evaluation import (
    EvaluationContext,
    EvaluationResult,
    EvaluationRunner,
    evaluation_test,
    run_evaluations,
)
from portkit.tidyllm.llm import LLMHelper, LLMMessage, LLMResponse, MockLLMClient, Role, ToolCall
from portkit.tidyllm.tools.calculator import calculator


class TestEvaluationDecorator:
    """Test the @evaluation_test decorator."""

    def test_decorator_marks_function(self):
        """Test that decorator properly marks functions."""

        @evaluation_test()
        def test_func():
            pass

        assert hasattr(test_func, "__evaluation_test__")
        assert test_func.__evaluation_test__ is True
        assert test_func.__evaluation_timeout__ == 30

    def test_decorator_with_custom_timeout(self):
        """Test decorator with custom timeout."""

        @evaluation_test(timeout_seconds=60)
        def test_func():
            pass

        assert test_func.__evaluation_timeout__ == 60


class TestEvaluationContext:
    """Test evaluation context and assertions."""

    def setup_method(self):
        """Set up test context."""
        library = FunctionLibrary(functions=[calculator])
        client = MockLLMClient()
        llm = LLMHelper("mock-model", library, client)
        self.context = EvaluationContext(llm)

    def test_assert_tool_called_success(self):
        """Test successful tool assertion."""
        tool_call = ToolCall(tool_name="calculator", tool_args={}, tool_result=Mock())
        response = LLMResponse(messages=[], tool_calls=[tool_call])

        self.context.assert_tool_called(response, "calculator")
        assert self.context._assertions_passed == 1
        assert self.context._assertions_total == 1

    def test_assert_tool_called_failure(self):
        """Test failed tool assertion."""
        tool_call = ToolCall(tool_name="wrong_tool", tool_args={}, tool_result=Mock())
        response = LLMResponse(messages=[], tool_calls=[tool_call])

        with pytest.raises(AssertionError, match="Expected tool 'calculator'"):
            self.context.assert_tool_called(response, "calculator")

        assert self.context._assertions_passed == 0
        assert self.context._assertions_total == 1

    def test_assert_success(self):
        """Test success assertion."""
        response = LLMResponse(messages=[], tool_calls=[])
        self.context.assert_success(response)

        assert self.context._assertions_passed == 1

    def test_assert_result_contains(self):
        """Test result contains assertion."""
        tool_call = ToolCall(tool_name="test", tool_args={}, tool_result="Hello World")
        response = LLMResponse(messages=[], tool_calls=[tool_call])

        self.context.assert_result_contains(response, "World")
        assert self.context._assertions_passed == 1

        with pytest.raises(AssertionError, match="Expected 'Missing'"):
            self.context.assert_result_contains(response, "Missing")

    def test_assert_result_equals(self):
        """Test result equals assertion."""
        tool_call = ToolCall(tool_name="test", tool_args={}, tool_result=42)
        response = LLMResponse(messages=[], tool_calls=[tool_call])

        self.context.assert_result_equals(response, 42)
        assert self.context._assertions_passed == 1

        with pytest.raises(AssertionError, match="Expected 100"):
            self.context.assert_result_equals(response, 100)


class TestEvaluationRunner:
    """Test evaluation runner functionality."""

    def setup_method(self):
        """Set up test runner."""
        library = FunctionLibrary(functions=[calculator])
        self.runner = EvaluationRunner(library)

    def test_discover_tests(self):
        """Test test discovery from modules."""
        # Create a mock module with evaluation tests
        mock_module = Mock()

        @evaluation_test()
        def test_func1():
            pass

        def regular_func():
            pass

        @evaluation_test()
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

        @evaluation_test()
        def test_success(context):
            # This should succeed with mock client
            pass

        result = self.runner.run_test(test_success, "mock", use_mock=True)

        assert isinstance(result, EvaluationResult)
        assert result.success is True
        assert result.test_name == "test_success"
        assert result.duration_ms >= 0
        assert result.error_message is None

    def test_run_test_failure(self):
        """Test failed test execution."""

        @evaluation_test()
        def test_failure():
            raise ValueError("Test error")

        result = self.runner.run_test(test_failure, "mock", use_mock=True)

        assert isinstance(result, EvaluationResult)
        assert result.success is False
        assert result.test_name == "test_failure"
        assert result.error_message and "Test error" in result.error_message

    def test_run_test_with_context(self):
        """Test running test that expects context parameter."""

        @evaluation_test()
        def test_with_context(context):
            assert context is not None
            assert hasattr(context, "llm")

        result = self.runner.run_test(test_with_context, "mock", use_mock=True)
        assert result.success is True

    def test_run_test_without_context(self):
        """Test running test that doesn't expect context."""

        @evaluation_test()
        def test_without_context():
            # Just a simple test without context parameter
            assert True

        result = self.runner.run_test(test_without_context, "mock", use_mock=True)
        assert result.success is True

    def test_run_tests_multiple(self):
        """Test running multiple tests."""

        @evaluation_test()
        def test1():
            pass

        @evaluation_test()
        def test2():
            pass

        @evaluation_test()
        def test_fail():
            raise RuntimeError("Intentional failure")

        results = self.runner.run_tests([test1, test2, test_fail], "mock", use_mock=True)

        assert isinstance(results, list)
        assert len(results) == 3
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        assert passed == 2
        assert failed == 1


class TestEvaluationIntegration:
    """Integration tests for the full evaluation system."""

    def test_run_evaluations_with_modules(self):
        """Test running evaluations with provided modules."""
        library = FunctionLibrary(functions=[calculator])

        # Create mock module with tests
        mock_module = Mock()

        @evaluation_test()
        def integration_test():
            assert True

        mock_module.__dict__ = {"integration_test": integration_test}

        # Mock dir() for test discovery
        import builtins

        original_dir = builtins.dir
        builtins.dir = lambda x: list(x.__dict__.keys())

        try:
            results = run_evaluations(
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

    def test_run_evaluations_no_tests(self):
        """Test running evaluations when no tests are found."""
        library = FunctionLibrary(functions=[calculator])
        mock_module = Mock()
        mock_module.__dict__ = {}

        import builtins

        original_dir = builtins.dir
        builtins.dir = lambda x: list(x.__dict__.keys())

        try:
            results = run_evaluations(
                function_library=library,
                model="mock",
                test_modules=[mock_module],
                mock_client=True,
            )

            assert len(results) == 0
        finally:
            builtins.dir = original_dir

    def test_run_evaluations_no_tests_found(self):
        """Test when no tests are found."""
        library = FunctionLibrary(functions=[calculator])

        results = run_evaluations(function_library=library, model="mock", mock_client=True)

        assert len(results) == 0
