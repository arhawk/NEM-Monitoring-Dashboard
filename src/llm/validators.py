from __future__ import annotations

import ast

FORBIDDEN_NAMES = frozenset(
    {
        "open",
        "exec",
        "eval",
        "__import__",
        "os",
        "sys",
        "subprocess",
        "compile",
        "globals",
        "locals",
        "getattr",
        "setattr",
        "delattr",
        "input",
        "help",
        "vars",
        "dir",
        "memoryview",
        "breakpoint",
    }
)


class _CodeValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.errors.append("import statements are not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.errors.append("import statements are not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES or node.id.startswith("__"):
            self.errors.append(f"forbidden name: {node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in FORBIDDEN_NAMES:
            self.errors.append(f"forbidden attribute access: {node.value.id}")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                if target.id != "result":
                    self.errors.append(
                        f"assignment to '{target.id}' is not allowed; only 'result' is permitted"
                    )
            else:
                self.errors.append("only simple assignment to 'result' is allowed")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.errors.append("augmented assignment is not allowed")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.errors.append("annotated assignment is not allowed")
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        self.errors.append("delete statements are not allowed")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.errors.append("function definitions are not allowed")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.errors.append("function definitions are not allowed")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.errors.append("class definitions are not allowed")
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.errors.append("lambda expressions are not allowed")
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.errors.append("comprehensions are not allowed")
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self.errors.append("comprehensions are not allowed")
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.errors.append("comprehensions are not allowed")
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self.errors.append("comprehensions are not allowed")
        self.generic_visit(node)


def _count_code_lines(code: str) -> int:
    count = 0
    for line in code.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def validate_analysis_code(code: str) -> None:
    if not code or not code.strip():
        raise ValueError("Generated code is empty.")

    if _count_code_lines(code) > 10:
        raise ValueError("Generated code exceeds the 10-line limit.")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"Generated code has invalid syntax: {exc}") from exc

    validator = _CodeValidator()
    validator.visit(tree)

    if validator.errors:
        raise ValueError("; ".join(validator.errors))

    assigns_result = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "result"
            for target in node.targets
        )
        for node in ast.walk(tree)
    )
    if not assigns_result:
        raise ValueError("Generated code must assign to 'result'.")


__all__ = ["validate_analysis_code"]
