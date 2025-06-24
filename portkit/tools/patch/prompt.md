Apply diff-fenced patches to source files.

Patches use the aider diff-fenced format:

```
path/to/file
<<<<<<< SEARCH
old content to search for
=======
new content to replace with
>>>>>>> REPLACE
```

Multiple search/replace blocks can be included in a single patch.
Patches are applied in the order specified.
Patches may be partially applied.
Prefer to use multiple search/replace blocks over a single large patch.

Example patch:
```
rust/src/foo.rs
<<<<<<< SEARCH
fn old_function() {
    println!("old");
}
=======
fn new_function() {
    println!("new");
}
>>>>>>> REPLACE

rust/src/bar.rs
<<<<<<< SEARCH
let x = 1;
=======
let x = 2;
>>>>>>> REPLACE
```

After the patch is applied, lib.rs and Cargo.toml will be automatically updated
to import the module into the project (if it wasn't already), and to add a bin
entry for any new fuzz tests.