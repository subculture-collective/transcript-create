# HasanAra Architecture Language

Use these terms exactly in architecture review, implementation plans, and refactor notes.

- **Module**: Anything with an interface and an implementation: a function, class, package, feature slice, route group, worker workflow, or frontend kernel.
- **Interface**: Everything a caller must know to use the Module: types, invariants, error modes, ordering, configuration, side effects, and lifecycle. The interface is not just the type signature.
- **Implementation**: The code inside a Module that callers should not need to know in order to use it correctly.
- **Depth**: Leverage at the interface: a lot of behavior behind a small interface. A **Deep** Module has high leverage. A **Shallow** Module has an interface nearly as complex as its implementation.
- **Seam**: Where an interface lives; a place behavior can be altered without editing callers in place.
- **Adapter**: A concrete Module satisfying an interface at a seam, often translating between HasanAra domain code and an external tool, database, subprocess, or browser API.
- **Leverage**: What callers get from depth: they can ask for a useful outcome without learning or duplicating the internal workflow.
- **Locality**: What maintainers get from depth: change, bugs, tests, and knowledge concentrated in one place.
- **Deletion test**: Imagine deleting the Module. If complexity vanishes, it was likely a pass-through. If complexity reappears across several callers, the Module was earning its keep.

## Review Rules

- The interface is the test surface.
- One adapter is a hypothetical seam. Two adapters make the seam real.
- Prefer naming Modules after HasanAra domain terms from `CONTEXT.md`.
