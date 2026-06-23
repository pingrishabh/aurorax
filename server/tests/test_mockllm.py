"""Unit tests for the mock-LLM: tokenization and steer keyword routing."""
import pytest

from app.mockllm import POOLS, select_pool, tokenize


def test_pools_nonempty():
    assert POOLS and all(text.strip() for text in POOLS.values())


@pytest.mark.parametrize("name", list(POOLS))
def test_tokenize_roundtrip(name):
    # Joining the streamed tokens must reproduce the source text exactly, so a
    # reconnecting client that concatenates tokens sees the real content.
    text = POOLS[name]
    assert "".join(tokenize(text)) == text


def test_tokenize_empty():
    assert tokenize("") == [""]


@pytest.mark.parametrize(
    "instruction,expected",
    [
        ("make it shorter", "concise"),
        ("tldr please", "concise"),
        ("explain in more detail", "detailed"),
        ("go deeper / elaborate", "detailed"),
        ("say it in French", "french"),
        ("as a haiku", "haiku"),
        ("write a poem", "haiku"),
        ("be a pirate", "pirate"),
        ("make it fun and exciting", "excited"),
    ],
)
def test_select_pool_keywords(instruction, expected):
    assert select_pool(instruction) in POOLS
    assert select_pool(instruction) == expected


def test_select_pool_no_keyword_rotates_to_a_real_pool():
    # No keyword should still pick *some* different style so steering is visible.
    for _ in range(4):
        assert select_pool("hmm interesting thought") in POOLS
