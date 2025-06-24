"""Benchmark framework for testing TidyAgent tools with LLMs."""

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ParamSpec, Protocol, TypeVar, cast, overload

from portkit.tidyllm import FunctionLibrary
from portkit.tidyllm.llm import LLMHelper, LLMResponse, create_llm_client
from portkit.tidyllm.registry import REGISTRY

P = ParamSpec("P")
T = TypeVar("T", covariant=True)


class CallableBenchmarkTest(Protocol[P, T]):
    """Protocol for benchmark test functions."""
    
    __benchmark_test__: bool
    __benchmark_timeout__: int
    
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T: ...


@dataclass
class BenchmarkResult:
    """Result of running a single benchmark test."""

    test_name: str
    success: bool
    duration_ms: int
    llm_response: LLMResponse | None = None
    error_message: str | None = None
    assertions_passed: int = 0
    assertions_total: int = 0


@overload
def benchmark_test(
    func_or_timeout: Callable[P, T],
) -> CallableBenchmarkTest[P, T]: ...

@overload
def benchmark_test(
    func_or_timeout: None = None,
    *,
    timeout_seconds: int = 30,
) -> Callable[[Callable[P, T]], CallableBenchmarkTest[P, T]]: ...

def benchmark_test(
    func_or_timeout: Callable[P, T] | None = None,
    *,
    timeout_seconds: int = 30,
) -> CallableBenchmarkTest[P, T] | Callable[[Callable[P, T]], CallableBenchmarkTest[P, T]]:
    """Decorator to mark a function as a benchmark test.

    Can be used with or without parentheses:
        @benchmark_test
        def my_test(...): ...
        
        @benchmark_test()
        def my_test(...): ...
        
        @benchmark_test(timeout_seconds=60)
        def my_test(...): ...

    Args:
        func_or_timeout: Function (when used without parentheses)
        timeout_seconds: Timeout in seconds for the test
    """
    
    def _mark_benchmark_test(func: Callable[P, T], timeout: int = 30) -> CallableBenchmarkTest[P, T]:
        func.__benchmark_test__ = True
        func.__benchmark_timeout__ = timeout
        return cast(CallableBenchmarkTest[P, T], func)
    
    # If first argument is a callable, this is direct usage (@benchmark_test)
    if callable(func_or_timeout):
        return _mark_benchmark_test(func_or_timeout, timeout_seconds)
    
    # Otherwise, this is parameterized usage (@benchmark_test() or @benchmark_test(timeout_seconds=60))
    def decorator(func: Callable[P, T]) -> CallableBenchmarkTest[P, T]:
        return _mark_benchmark_test(func, timeout_seconds)
    
    return decorator


class BenchmarkContext:
    """Context object provided to benchmark tests."""

    def __init__(self, llm: LLMHelper):
        self.llm = llm
        self._assertions_passed = 0
        self._assertions_total = 0
        self._test_name = ""

    def assert_tool_called(self, response: LLMResponse, expected_tool: str):
        """Assert that the expected tool was called."""
        self._assertions_total += 1
        if any(
            tool_call.tool_name == expected_tool for tool_call in response.tool_calls
        ):
            self._assertions_passed += 1
        else:
            raise AssertionError(
                f"Expected tool '{expected_tool}', but got '{[tool_call.tool_name for tool_call in response.tool_calls]}'"
            )

    def assert_success(self, response: LLMResponse):
        """Assert that the LLM response was successful."""
        self._assertions_total += 1
        if response.success:
            self._assertions_passed += 1
        else:
            raise AssertionError(f"LLM response failed: {response.error_message}")

    def assert_result_contains(self, response: LLMResponse, expected_value: Any):
        """Assert that the tool result contains the expected value."""
        self._assertions_total += 1
        if any(
            expected_value in str(tool_call.tool_result)
            for tool_call in response.tool_calls
        ):
            self._assertions_passed += 1
        else:
            raise AssertionError(
                f"Expected '{expected_value}' in result, got: {[tool_call.tool_result for tool_call in response.tool_calls]}"
            )

    def assert_result_equals(self, response: LLMResponse, expected_value: Any):
        """Assert that the tool result equals the expected value."""
        self._assertions_total += 1
        if any(
            tool_call.tool_result == expected_value for tool_call in response.tool_calls
        ):
            self._assertions_passed += 1
        else:
            raise AssertionError(
                f"Expected {expected_value}, got: {[tool_call.tool_result for tool_call in response.tool_calls]}"
            )


class BenchmarkRunner:
    """Runner for executing benchmark tests."""

    def __init__(self, function_library: FunctionLibrary):
        self.function_library = function_library

    def discover_tests(self, test_modules: list[Any]) -> list[Callable]:
        """Discover benchmark tests in the provided modules.

        Args:
            test_modules: List of Python modules containing benchmark tests

        Returns:
            List of test functions marked with @benchmark_test
        """
        tests = []

        for module in test_modules:
            for name in dir(module):
                obj = getattr(module, name)
                if callable(obj) and hasattr(obj, "__benchmark_test__") and obj.__benchmark_test__:
                    tests.append(obj)

        return tests

    def run_test(self, test_func: Callable, model: str, use_mock: bool = False) -> BenchmarkResult:
        """Run a single benchmark test.

        Args:
            test_func: Test function to execute
            model: LLM model to use for testing
            use_mock: Whether to use a mock LLM client for testing

        Returns:
            BenchmarkResult with test execution details
        """
        start_time = time.time()
        test_name = getattr(test_func, "__name__", str(test_func))

        try:
            # Get test configuration
            getattr(test_func, "__benchmark_timeout__", 30)

            # Create LLM client and helper
            if use_mock:
                from portkit.tidyllm.llm import MockLLMClient

                llm_client = MockLLMClient()
            else:
                llm_client = create_llm_client("litellm")

            llm_helper = LLMHelper(
                model=model,
                function_library=self.function_library,
                llm_client=llm_client,
            )

            # Create test context
            context = BenchmarkContext(llm_helper)
            context._test_name = test_name

            # Execute the test function
            # Check if test function expects context parameter
            sig = inspect.signature(test_func)
            if len(sig.parameters) > 0:
                test_func(context)
            else:
                test_func()

            duration_ms = int((time.time() - start_time) * 1000)

            return BenchmarkResult(
                test_name=test_name,
                success=True,
                duration_ms=duration_ms,
                assertions_passed=context._assertions_passed,
                assertions_total=context._assertions_total,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return BenchmarkResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                error_message=str(e),
                assertions_passed=getattr(context, "_assertions_passed", 0),
                assertions_total=getattr(context, "_assertions_total", 0),
            )

    def run_tests(
        self,
        tests: list[Callable],
        model: str,
        use_mock: bool = False,
    ) -> list[BenchmarkResult]:
        """Run multiple benchmark tests and collect results.

        Args:
            tests: List of test functions to execute
            model: LLM model to use for testing
            use_mock: Whether to use a mock LLM client for testing

        Returns:
            List of BenchmarkResult objects
        """
        results = []

        for test_func in tests:
            result = self.run_test(test_func, model, use_mock)
            results.append(result)

            # Print progress
            status = "PASS" if result.success else "FAIL"
            print(f"{status}: {result.test_name} ({result.duration_ms}ms)")
            if not result.success:
                print(f"  Error: {result.error_message}")

        return results

    def print_summary(self, results: list[BenchmarkResult]):
        """Print a summary of benchmark results.

        Args:
            results: List of BenchmarkResult objects
        """
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        success_rate = (passed / len(results)) * 100 if results else 0.0

        print("\n=== Benchmark Summary ===")
        print(f"Total tests: {len(results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success rate: {success_rate:.1f}%")

        if failed > 0:
            print("\nFailed tests:")
            for result in results:
                if not result.success:
                    print(f"  - {result.test_name}: {result.error_message}")


def run_benchmarks(
    function_library: FunctionLibrary,
    model: str,
    test_modules: list[Any] | None = None,
    mock_client: bool = False,
) -> list[BenchmarkResult]:
    """Convenience function to run benchmarks.

    Args:
        function_library: FunctionLibrary with registered tools
        model: LLM model to use for testing
        test_modules: List of modules containing benchmark tests
        test_path: Path to discover tests from
        mock_client: Whether to use mock LLM client

    Returns:
        List of BenchmarkResult objects
    """
    runner = BenchmarkRunner(function_library)

    # Discover tests
    if test_modules:
        tests = runner.discover_tests(test_modules)
    else:
        tests = []

    if not tests:
        print("No benchmark tests found")
        return []

    # Run tests
    results = runner.run_tests(tests, model, mock_client)
    runner.print_summary(results)

    return results


def main():
    """Main function to run benchmarks from command line arguments."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run TidyAgent benchmark tests")
    parser.add_argument("files", nargs="+", help="Python files containing benchmark tests")
    parser.add_argument("--model", required=True, help="LLM model to use for testing")

    args = parser.parse_args()

    # Import each test file as a module and collect tests
    test_modules = []
    for file_path in args.files:
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(Path(file_path).stem, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                test_modules.append(module)
        except Exception as e:
            print(f"Error importing {file_path}: {e}")
            sys.exit(1)

    # build the library using all function descriptions in the registry
    library = FunctionLibrary(function_descriptions=REGISTRY.functions)

    # Run benchmarks
    try:
        results = run_benchmarks(
            function_library=library,
            model=args.model,
            test_modules=test_modules,
        )

        # Exit with error code if any tests failed
        failed_count = sum(1 for r in results if not r.success)
        if failed_count > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"Benchmark execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
