"""Shared, task-independent coding guidance. Contains no benchmark solutions."""

POLICY_VERSION = 'contract-review-v2'
CONTRACT_CHECKS = (
    'Follow the specification and its examples over familiar problem names. '
    'Keep supplied working helper functions unchanged. Do not invent input restrictions '
    'or special-case returns. Before answering, silently trace the given examples '
    'through your implementation and check every required condition and branch. '
    'Distinguish values from indices and counts from totals; preserve exact return '
    'types, string formatting, ordering and tie rules. Derive bounds, signs and '
    'duplicate semantics from the task. Verify loop progress, termination and residual '
    'elements, required imports, and the mathematical formula. '
)

# The strict generation/evaluation contract stays byte-for-byte unchanged.
# Interactive analysis requests use the checks without forcing an implementation.
CONTRACT_REVIEW = CONTRACT_CHECKS + (
    'Return only the requested implementation; do not print reasoning or claim unperformed tests.'
)

PYTHON_SYSTEM = (
    'Write a complete Python 3.11 implementation including required imports. '
    'Preserve requested signatures and supplied working helpers. '
    + CONTRACT_REVIEW +
    ' Return exactly one complete Python code block. No placeholders or explanation.'
)


def failure_feedback(record):
    """Prefer the Python exception over the unhelpful outer Wasmtime trap."""
    output = str(record.get('output') or '').strip()
    error = str(record.get('error') or '').strip()
    if 'wasm trap: interrupt' in error:
        return 'Execution exceeded the 10-second WASI limit. Check termination and complexity.'
    if output:
        # Python exceptions appear at the end, after any candidate prints.
        return output[-2400:]
    return error[-2400:] or 'User checks did not finish successfully.'
