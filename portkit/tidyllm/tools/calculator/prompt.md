# Calculator Tool

Perform basic mathematical calculations with two numeric operands.

## Supported Operations

- **add**: Addition (left + right)
- **subtract**: Subtraction (left - right) 
- **multiply**: Multiplication (left * right)
- **divide**: Division (left / right, with zero-division protection)

## Parameters

- **operation** (required): The mathematical operation to perform
  - Valid values: "add", "subtract", "multiply", "divide"
- **left** (required): First number (left operand)
  - Type: number (integer or float)
- **right** (required): Second number (right operand)  
  - Type: number (integer or float)

## Examples

### Addition
```json
{
  "operation": "add",
  "left": 10,
  "right": 5
}
```
Result: `15` with expression `"10 + 5 = 15"`

### Subtraction
```json
{
  "operation": "subtract", 
  "left": 10,
  "right": 3
}
```
Result: `7` with expression `"10 - 3 = 7"`

### Multiplication
```json
{
  "operation": "multiply",
  "left": 4,
  "right": 6
}
```
Result: `24` with expression `"4 * 6 = 24"`

### Division
```json
{
  "operation": "divide",
  "left": 15,
  "right": 3
}
```
Result: `5` with expression `"15 / 3 = 5"`

## Return Value

The tool returns a `CalculatorResult` object with:
- **result**: The calculated numeric result
- **operation**: The operation that was performed
- **expression**: A human-readable expression showing the calculation

## Error Handling

- **Division by zero**: Returns error when `right` operand is 0 for division
- **Invalid operation**: Returns error for unsupported operation types
- **Invalid operands**: Validates that left and right are numeric values

## Usage Notes

1. All operations work with both integers and floating-point numbers
2. Division results are always floating-point numbers
3. The tool provides clear expression strings for logging/display
4. All errors are handled gracefully with descriptive messages