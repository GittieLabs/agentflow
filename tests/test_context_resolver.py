"""Tests for ContextProfile schema, ConfigLoader profile detection, and ContextResolver."""
import pytest

from agentflow.config.loader import ConfigLoader
from agentflow.config.resolver import ContextResolver
from agentflow.config.schemas import ConditionalInclude, ContextProfile


# ── Schema tests ─────────────────────────────────────────────────────────────


def test_context_profile_schema():
    profile = ContextProfile(
        type="profile",
        includes=["shared/persona-keith.context.md"],
        conditionalIncludes=[
            ConditionalInclude(
                **{"if": "'blog' in message", "include": "shared/content-guidelines.context.md"}
            ),
        ],
    )
    assert profile.type == "profile"
    assert len(profile.includes) == 1
    assert len(profile.conditional_includes) == 1
    assert profile.conditional_includes[0].condition == "'blog' in message"


def test_conditional_include_list_normalization():
    """Single string include gets normalized to a list."""
    ci = ConditionalInclude(**{"if": "'test' in message", "include": "single-file.context.md"})
    assert ci.include_list() == ["single-file.context.md"]

    ci_multi = ConditionalInclude(
        **{"if": "'test' in message", "include": ["file-a.context.md", "file-b.context.md"]}
    )
    assert ci_multi.include_list() == ["file-a.context.md", "file-b.context.md"]


def test_context_profile_defaults():
    profile = ContextProfile(type="profile")
    assert profile.includes == []
    assert profile.conditional_includes == []


# ── ConfigLoader profile detection ───────────────────────────────────────────


def _setup_context_dir(tmp_path):
    """Create a context directory with profiles and regular context files."""
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    # Regular context file
    (shared_dir / "persona-keith.context.md").write_text(
        "---\n---\nKeith is a software engineer and entrepreneur."
    )

    # Another regular context file
    (shared_dir / "content-guidelines.context.md").write_text(
        "---\n---\nWrite in a conversational, authoritative tone."
    )

    # Lead gen config
    (shared_dir / "lead-gen-config.context.md").write_text(
        "---\n---\nDefault batch size: 50. Validation threshold: 95%."
    )

    # Profile context file (the new feature)
    (shared_dir / "content-profile.context.md").write_text(
        """---
type: profile
includes:
  - shared/persona-keith.context.md
conditionalIncludes:
  - if: "'blog' in message or 'article' in message"
    include: shared/content-guidelines.context.md
  - if: "'lead' in message"
    include:
      - shared/lead-gen-config.context.md
---
Content profile: loads persona always, guidelines for content tasks, lead config for lead gen.
"""
    )

    # Agent prompt
    (agents_dir / "test.prompt.md").write_text(
        """---
name: test_agent
context_files:
  - shared/content-profile.context.md
---
You are a test agent.
"""
    )

    return tmp_path


def test_loader_detects_profiles(tmp_path):
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    # Profile should be detected
    assert loader.is_profile("shared/content-profile.context.md")
    profile = loader.get_profile("shared/content-profile.context.md")
    assert profile is not None
    assert profile.type == "profile"
    assert len(profile.includes) == 1
    assert len(profile.conditional_includes) == 2

    # Regular files should NOT be profiles
    assert not loader.is_profile("shared/persona-keith.context.md")
    assert not loader.is_profile("shared/content-guidelines.context.md")

    # But regular files should still have bodies
    assert loader.get_context_body("shared/persona-keith.context.md") is not None
    assert "software engineer" in loader.get_context_body("shared/persona-keith.context.md")


def test_loader_profile_body_also_stored(tmp_path):
    """Profile files store both the ContextProfile and the body text."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    body = loader.get_context_body("shared/content-profile.context.md")
    assert body is not None
    assert "Content profile" in body


# ── ContextResolver ──────────────────────────────────────────────────────────


def test_resolver_regular_file(tmp_path):
    """Resolving a non-profile file returns its body directly."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    result = resolver.resolve(["shared/persona-keith.context.md"])

    assert len(result) == 1
    assert "software engineer" in result[0]


def test_resolver_profile_always_includes(tmp_path):
    """Profile's `includes` files are always loaded."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    # No message context — only always-includes should resolve
    result = resolver.resolve(["shared/content-profile.context.md"])

    # Should include: profile body + persona (always-included)
    combined = "\n".join(result)
    assert "Content profile" in combined
    assert "software engineer" in combined
    # Should NOT include content-guidelines (conditional, no message match)
    assert "conversational" not in combined


def test_resolver_profile_conditional_match(tmp_path):
    """Conditional includes load when condition matches."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    result = resolver.resolve(
        ["shared/content-profile.context.md"],
        runtime_context={"message": "Write a blog post about AI agents"},
    )

    combined = "\n".join(result)
    # Always-included
    assert "software engineer" in combined
    # Conditional match: 'blog' in message
    assert "conversational" in combined
    # NOT matched: 'lead' not in message
    assert "batch size" not in combined


def test_resolver_profile_conditional_lead_match(tmp_path):
    """Lead gen conditional includes load when 'lead' is in message."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    result = resolver.resolve(
        ["shared/content-profile.context.md"],
        runtime_context={"message": "Find new leads for Hatchworks"},
    )

    combined = "\n".join(result)
    # Always-included
    assert "software engineer" in combined
    # Conditional match: 'lead' in message
    assert "batch size" in combined
    # NOT matched: 'blog'/'article' not in message
    assert "conversational" not in combined


def test_resolver_profile_or_condition(tmp_path):
    """'or' in condition: either keyword triggers the include."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)

    # 'article' should also trigger the content-guidelines include
    result = resolver.resolve(
        ["shared/content-profile.context.md"],
        runtime_context={"message": "Draft an article about AI trends"},
    )
    combined = "\n".join(result)
    assert "conversational" in combined


def test_resolver_no_duplicates(tmp_path):
    """Same file referenced multiple times only appears once."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    # Reference persona directly AND through the profile (which includes it)
    result = resolver.resolve([
        "shared/persona-keith.context.md",
        "shared/content-profile.context.md",
    ])

    # Count how many times persona text appears
    persona_count = sum(1 for r in result if "software engineer" in r)
    assert persona_count == 1


def test_resolver_missing_file(tmp_path):
    """Missing context file is logged and skipped, no error."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    result = resolver.resolve(["shared/nonexistent.context.md"])
    assert result == []


def test_resolver_has_profiles(tmp_path):
    """has_profiles() detects whether context_files contain any profiles."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    assert resolver.has_profiles(["shared/content-profile.context.md"])
    assert not resolver.has_profiles(["shared/persona-keith.context.md"])
    assert resolver.has_profiles([
        "shared/persona-keith.context.md",
        "shared/content-profile.context.md",
    ])


def test_resolver_mixed_refs(tmp_path):
    """Mix of regular files and profiles resolves correctly."""
    ctx_dir = _setup_context_dir(tmp_path)
    loader = ConfigLoader(ctx_dir)
    loader.load()

    resolver = ContextResolver(loader)
    result = resolver.resolve(
        [
            "shared/lead-gen-config.context.md",
            "shared/content-profile.context.md",
        ],
        runtime_context={"message": "Write a blog post"},
    )

    combined = "\n".join(result)
    # Direct ref
    assert "batch size" in combined
    # Profile body
    assert "Content profile" in combined
    # Profile always-include
    assert "software engineer" in combined
    # Profile conditional match (blog)
    assert "conversational" in combined
