"""
Chroma persistence smoke test for Agent Forge.

Verifies that Chroma can:
- Create or open a persistent collection
- Insert a document
- Retrieve by similarity
- Delete a temporary collection
"""

import contextlib
import shutil
from pathlib import Path

import pytest


@pytest.mark.integration
def test_chroma_smoke() -> None:
    """
    Smoke test for Chroma persistence.

    Creates a temporary collection, inserts a document, retrieves it,
    and cleans up afterward.
    """
    # Use a test-specific directory
    test_persist_dir = "./chroma_data_test"

    try:
        # Import here to allow graceful skip if dependencies not installed
        import chromadb

        # Test 1: Create or open persistent client
        try:
            client = chromadb.PersistentClient(path=test_persist_dir)
            print("✓ Test 1: PersistentClient created successfully")
        except Exception as e:
            pytest.fail(f"Failed to create PersistentClient: {e}")

        # Test 2: Create a temporary collection
        collection_name = "test_smoke_collection"
        try:
            # Delete if exists from previous run; absent is the normal case
            with contextlib.suppress(Exception):
                client.delete_collection(name=collection_name)

            collection = client.create_collection(
                name=collection_name,
                metadata={"description": "Temporary smoke test collection"},
            )
            print("✓ Test 2: Collection created successfully")
        except Exception as e:
            pytest.fail(f"Failed to create collection: {e}")

        # Test 3: Insert a document
        try:
            collection.add(
                documents=["Agent Forge is a safe client deployment automation tool."],
                metadatas=[{"source": "smoke_test", "type": "description"}],
                ids=["smoke_test_doc_1"],
            )
            print("✓ Test 3: Document inserted successfully")
        except Exception as e:
            pytest.fail(f"Failed to insert document: {e}")

        # Test 4: Retrieve by similarity
        try:
            results = collection.query(query_texts=["What is Agent Forge?"], n_results=1)

            assert results is not None
            assert "documents" in results
            assert len(results["documents"]) > 0
            assert len(results["documents"][0]) > 0

            retrieved_doc = results["documents"][0][0]
            assert "Agent Forge" in retrieved_doc
            assert "deployment" in retrieved_doc

            print("✓ Test 4: Document retrieved successfully by similarity")
        except Exception as e:
            pytest.fail(f"Failed to retrieve document: {e}")

        # Test 5: Delete the temporary collection
        try:
            client.delete_collection(name=collection_name)
            print("✓ Test 5: Temporary collection deleted successfully")
        except Exception as e:
            pytest.fail(f"Failed to delete collection: {e}")

        # Verify collection is gone
        try:
            collections = client.list_collections()
            collection_names = [c.name for c in collections]
            assert collection_name not in collection_names
            print("✓ Test 6: Collection deletion verified")
        except Exception as e:
            pytest.fail(f"Failed to verify collection deletion: {e}")

        print("\n✅ Chroma persistence: PASS")
        print("All smoke tests passed. Chroma is working correctly.")

    finally:
        # Release client before cleanup to avoid Windows file locks
        if "client" in dir():
            del client
        import gc

        gc.collect()

        # Clean up test directory
        if Path(test_persist_dir).exists():
            try:
                shutil.rmtree(test_persist_dir)
                print(f"✓ Cleaned up test directory: {test_persist_dir}")
            except PermissionError:
                # Windows may hold file locks briefly after client release
                import time

                time.sleep(0.5)
                try:
                    shutil.rmtree(test_persist_dir)
                    print(f"✓ Cleaned up test directory (retry): {test_persist_dir}")
                except PermissionError:
                    print(f"⚠ Could not clean {test_persist_dir} (locked) - harmless")


if __name__ == "__main__":
    # Allow running directly for manual testing
    test_chroma_smoke()
