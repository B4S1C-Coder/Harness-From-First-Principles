# harness/sandboxes

## Purpose
- Provide a filesystem view rooted at one directory for listing, reading, writing, and editing files.

## Public interface
- Package export: `VirtualFileSystemSandbox(root: Path, can_read: bool = True, can_write: bool = False, can_execute: bool = False)`; frozen dataclass.
- `resolve(path: str, *, must_exist: bool = True) -> Path`
- `list_directory(path: str = ".") -> str`
- `read_file(path: str, *, max_bytes: int = 64 * 1024) -> str`
- `read_lines(path: str, *, start_line: int, end_line: int, max_bytes: int = 64 * 1024, max_lines: int = 200) -> str`
- `write_file(path: str, content: str, *, overwrite: bool = False) -> None`
- `edit_file(path: str, *, start_line: int, end_line: int, content: str) -> None`
- Module helper: `virtual_fsb.human_size(size: int) -> str`.

## Contracts
- Construction requires an existing directory; `root` becomes an expanded, resolved absolute path.
- Paths must be relative and resolve within `root`; `resolve` itself does not enforce read/write flags.
- Listing requires reading permission and directory access; entries are sorted by name, with permissions, size, local modification time, and name. Symlinks and special files are omitted.
- Reads decode UTF-8 with replacement, require positive byte limits, and append a truncation marker when capped.
- `read_lines` uses inclusive, one-based ranges, prefixes returned lines with their numbers, and enforces positive limits and the requested line-count cap; ranges beyond EOF return available lines.
- Writing requires `can_write`, writes UTF-8, and creates a file or truncates it when `overwrite=True`; parent directories are not created.
- Editing requires both read and write flags, reads strict UTF-8, and replaces an inclusive, one-based range within the file; nonempty replacement content gains a trailing newline if absent. Empty content deletes the range.
- Raises `harness.exceptions.PermissionDenied` for disabled operations, absolute/escaping paths, and explicit access failures; `NotADirectory` for invalid root/listing targets; `ToolExecutionError` for non-file targets; `ValueValidationError` for invalid ranges or limits.
- Filesystem and strict decoding errors propagate, including missing paths and existing files when overwrite is disabled; writes and edits change real files.

## Dependencies
- Imports `harness.exceptions`; no other harness package imports.

## Testing
- no tests

## Gotchas
- Intended for trusted, single-user environments; path checks and filesystem operations are vulnerable to TOCTOU races and malicious local processes.
- Provides no OS isolation or execution facility; `can_execute` only affects displayed file permissions. Directory traversal display depends on `can_read`.
- Listings hide symlinks, but direct paths may follow symlinks whose resolved targets remain inside the root.
