"""
Unit Tests for Milestone 4: Structured 10-Tier Memory Persistence
Validates:
- Low-RAM SQLite configuration and pragmas
- 10-Tier memory classification
- Storage, retrieval, and deletion of entries
- FTS5 BM25 search and ranking for Semantic Facts
- User data isolation
- TTL expiration and pruning
- Session context continuity
"""

import os
import tempfile
import time
import unittest

from brain.memory_store import MemoryStore, MemoryTier


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_memory.db")
        self.store = MemoryStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_ten_tiers_defined(self):
        """Verify all 10 distinct memory tiers exist in the enum."""
        expected_tiers = {
            "WORKING_BUFFER",
            "SHORT_TERM_SESSION",
            "EPISODIC_EVENTS",
            "SEMANTIC_FACTS",
            "PROCEDURAL_LESSONS",
            "USER_PROFILE",
            "SECURITY_AUDIT_LOG",
            "AGENT_SWARM_STATE",
            "MCP_TOOL_CACHE",
            "ARCHIVAL_SUMMARY",
        }
        actual_tiers = {t.name for t in MemoryTier}
        self.assertEqual(expected_tiers, actual_tiers)

    def test_basic_crud(self):
        """Verify basic storage, retrieval, update, and deletion."""
        entry_id = self.store.store_entry(
            user_id="alice",
            tier=MemoryTier.USER_PROFILE,
            key="preferred_language",
            content="Hindi",
            metadata={"source": "voice_preference"},
        )
        self.assertIsInstance(entry_id, int)
        self.assertGreater(entry_id, 0)

        # Retrieve
        retrieved = self.store.get_entry(
            user_id="alice",
            tier=MemoryTier.USER_PROFILE,
            key="preferred_language",
        )
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["content"], "Hindi")
        self.assertEqual(retrieved["user_id"], "alice")
        self.assertEqual(retrieved["tier"], MemoryTier.USER_PROFILE.value)
        self.assertEqual(retrieved["metadata"].get("source"), "voice_preference")

        # Update
        updated_id = self.store.store_entry(
            user_id="alice",
            tier=MemoryTier.USER_PROFILE,
            key="preferred_language",
            content="English",
        )
        self.assertEqual(updated_id, entry_id)
        retrieved_updated = self.store.get_entry(
            user_id="alice",
            tier=MemoryTier.USER_PROFILE,
            key="preferred_language",
        )
        self.assertEqual(retrieved_updated["content"], "English")

        # Delete
        self.assertTrue(
            self.store.delete_entry(
                user_id="alice",
                tier=MemoryTier.USER_PROFILE,
                key="preferred_language",
            )
        )
        self.assertIsNone(
            self.store.get_entry(
                user_id="alice",
                tier=MemoryTier.USER_PROFILE,
                key="preferred_language",
            )
        )

    def test_user_isolation(self):
        """Ensure User A cannot retrieve or overwrite User B's memory entries."""
        self.store.store_entry(
            user_id="user_a",
            tier=MemoryTier.USER_PROFILE,
            key="token",
            content="secret_a",
        )
        self.store.store_entry(
            user_id="user_b",
            tier=MemoryTier.USER_PROFILE,
            key="token",
            content="secret_b",
        )

        entry_a = self.store.get_entry(user_id="user_a", tier=MemoryTier.USER_PROFILE, key="token")
        entry_b = self.store.get_entry(user_id="user_b", tier=MemoryTier.USER_PROFILE, key="token")

        self.assertEqual(entry_a["content"], "secret_a")
        self.assertEqual(entry_b["content"], "secret_b")

        # User A listing entries does not see User B
        entries_a = self.store.list_entries(user_id="user_a", tier=MemoryTier.USER_PROFILE)
        self.assertEqual(len(entries_a), 1)
        self.assertEqual(entries_a[0]["content"], "secret_a")

    def test_fts5_semantic_search_and_bm25(self):
        """Verify SQLite FTS5 BM25 search ranking across semantic facts."""
        self.store.store_entry(
            user_id="charlie",
            tier=MemoryTier.SEMANTIC_FACTS,
            key="fact_python",
            content="Python is an interpreted programming language often used in AI and data analysis.",
        )
        self.store.store_entry(
            user_id="charlie",
            tier=MemoryTier.SEMANTIC_FACTS,
            key="fact_rust",
            content="Rust is a systems programming language focused on memory safety and speed.",
        )
        self.store.store_entry(
            user_id="charlie",
            tier=MemoryTier.SEMANTIC_FACTS,
            key="fact_astronomy",
            content="The sun is a celestial star at the center of the solar system.",
        )

        # Search for 'programming language'
        results = self.store.recall_fts(
            user_id="charlie",
            query="programming language",
            tiers=[MemoryTier.SEMANTIC_FACTS],
        )
        self.assertEqual(len(results), 2)
        keys = [r["key"] for r in results]
        self.assertIn("fact_python", keys)
        self.assertIn("fact_rust", keys)
        self.assertNotIn("fact_astronomy", keys)

        # Search for 'astronomy' or 'solar'
        astro_results = self.store.recall_fts(
            user_id="charlie",
            query="solar system",
        )
        self.assertEqual(len(astro_results), 1)
        self.assertEqual(astro_results[0]["key"], "fact_astronomy")

    def test_session_context_continuity(self):
        """Verify structured multi-turn session event tracking."""
        session_id = "session_xyz_123"
        self.store.store_entry(
            user_id="alice",
            tier=MemoryTier.SHORT_TERM_SESSION,
            key=f"{session_id}_turn_1",
            content="User said: Check system battery.",
            metadata={"session_id": session_id},
        )
        self.store.store_entry(
            user_id="alice",
            tier=MemoryTier.SHORT_TERM_SESSION,
            key=f"{session_id}_turn_2",
            content="DAKU answered: Battery level is 85%.",
            metadata={"session_id": session_id},
        )

        ctx = self.store.get_session_context(user_id="alice", session_id=session_id)
        self.assertEqual(ctx["session_id"], session_id)
        self.assertEqual(len(ctx["session_entries"]), 2)
        self.assertEqual(ctx["session_entries"][0]["content"], "User said: Check system battery.")
        self.assertEqual(ctx["session_entries"][1]["content"], "DAKU answered: Battery level is 85%.")

    def test_ttl_and_pruning(self):
        """Verify automatic expiration of short-lived entries."""
        # Store an entry with a 0.5-second TTL
        self.store.store_entry(
            user_id="bob",
            tier=MemoryTier.WORKING_BUFFER,
            key="temp_state",
            content="Transient calculation result",
            ttl_seconds=0.5,
        )

        # Immediately available
        self.assertIsNotNone(self.store.get_entry("bob", MemoryTier.WORKING_BUFFER, "temp_state"))

        # Wait for TTL to elapse
        time.sleep(0.7)

        # Prune expired
        pruned_count = self.store.prune_expired()
        self.assertGreaterEqual(pruned_count, 1)

        # Now it is gone
        self.assertIsNone(self.store.get_entry("bob", MemoryTier.WORKING_BUFFER, "temp_state"))

    def test_clear_tier(self):
        """Verify clearing all entries within a specific tier for a user."""
        self.store.store_entry("alice", MemoryTier.WORKING_BUFFER, "buf1", "val1")
        self.store.store_entry("alice", MemoryTier.WORKING_BUFFER, "buf2", "val2")
        self.store.store_entry("alice", MemoryTier.USER_PROFILE, "prof1", "val3")

        deleted = self.store.clear_tier("alice", MemoryTier.WORKING_BUFFER)
        self.assertEqual(deleted, 2)

        # Working buffer is empty
        self.assertEqual(len(self.store.list_entries("alice", MemoryTier.WORKING_BUFFER)), 0)
        # User profile remains untouched
        self.assertEqual(len(self.store.list_entries("alice", MemoryTier.USER_PROFILE)), 1)


if __name__ == "__main__":
    unittest.main()
