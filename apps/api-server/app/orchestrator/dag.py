"""Topological waves and goal ancestry for a delegation plan. Implements: REQ-002."""

from app.orchestrator.state import DAGTaskNode

MAX_HOPS = 8


def execution_waves(steps: list[DAGTaskNode]) -> list[list[DAGTaskNode]] | None:
    """Return parallel waves, or None when the plan has a cycle or a missing edge."""

    by_id = {step.step_id: step for step in steps}
    if len(by_id) != len(steps):
        return None
    indegree = {step.step_id: 0 for step in steps}
    dependents: dict[int, list[int]] = {step.step_id: [] for step in steps}
    for step in steps:
        for dependency in step.depends_on_steps:
            if dependency not in by_id:
                return None
            indegree[step.step_id] += 1
            dependents[dependency].append(step.step_id)
    ready = sorted(step_id for step_id, degree in indegree.items() if degree == 0)
    waves: list[list[DAGTaskNode]] = []
    seen = 0
    while ready:
        wave = [by_id[step_id] for step_id in ready]
        waves.append(wave)
        seen += len(wave)
        next_ready: list[int] = []
        for step_id in ready:
            for child in dependents[step_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_ready.append(child)
        ready = sorted(next_ready)
    if seen != len(steps):
        return None
    return waves


def ancestor_labels(step_id: int, by_id: dict[int, DAGTaskNode]) -> list[str]:
    """Transitive upstream labels, each role and title once, in dependency order."""

    labels: list[str] = []
    for dependency_id in by_id[step_id].depends_on_steps:
        for label in ancestor_labels(dependency_id, by_id):
            if label not in labels:
                labels.append(label)
        dependency = by_id[dependency_id]
        label = f"{dependency.target_role_code} {dependency.task_title}"
        if label not in labels:
            labels.append(label)
    return labels
