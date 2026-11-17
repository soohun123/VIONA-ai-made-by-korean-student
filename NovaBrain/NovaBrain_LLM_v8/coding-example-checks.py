# Executed by coding_workflow.py inside WASI only.
assert unique_in_order([]) == []
assert unique_in_order([7]) == [7]
assert unique_in_order([3, 1, 3, 2, 1]) == [3, 1, 2]
assert unique_in_order([0, -1, 0, -2, -1]) == [0, -1, -2]
items = [4, 4, 2, 4, 2, 1]
before = items.copy()
answer = unique_in_order(items)
assert answer == [4, 2, 1]
assert items == before
assert answer is not items
values = list(range(2000)) + list(range(2000))
assert unique_in_order(values) == list(range(2000))
