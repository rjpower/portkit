# Patch File Tool

Apply text modifications using unified diff patches. This tool can patch both inline text content and files on disk.

## Unified Diff Format

The patch_content must be in standard unified diff format:

```
--- a/filename
+++ b/filename
@@ -start_line,count +start_line,count @@
 context line
-line to remove
+line to add
 context line
```

## Parameters

- **patch_content** (required): The unified diff patch content
- **target_text** (optional): Text content to patch inline 
- **target_file** (optional): File path to patch on disk
- **dry_run** (optional): If true, validate patch without applying it

Either target_text OR target_file must be provided, but not both.

## Examples

### Simple Line Replacement
To change "hello world" to "hello universe":

```
@@ -1 +1 @@
-hello world
+hello universe
```

### Multi-line Replacement
To replace old function with new function:

```
@@ -1,4 +1,4 @@
-def old_function():
-    return "old"
+def new_function():
+    return "new"
 
 def main():
```

### Adding Lines
To add a line between existing lines:

```
@@ -1,2 +1,3 @@
 start
+middle
 end
```

### Removing Lines
To remove a line:

```
@@ -1,3 +1,2 @@
 keep this
-remove this
 keep this too
```

### Multiple Changes
Multiple @@ hunks can be included in one patch:

```
@@ -1 +1 @@
-foo is good
+apple is good
@@ -2 +2 @@
-bar is bad
+orange is bad
```

## Important Notes

1. **Context lines**: Include surrounding unchanged lines for better matching
2. **Line numbers**: @@ -old_start,old_count +new_start,new_count @@
3. **Prefixes**: Lines start with ' ' (context), '-' (remove), '+' (add)
4. **Exact matching**: Content must match exactly including whitespace
5. **Dry run**: Use dry_run=true to validate patches before applying

## Success Indicators

- result.success = true
- result.modified_content contains the patched text (for inline patches)
- result.lines_added/lines_removed show statistics
- result.hunks_applied shows number of successful hunks