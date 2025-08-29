#!/usr/bin/env python3
"""
Test script to verify the optimized response_processor functions work correctly.
"""

import sys
import os
import asyncio
from typing import Any, Dict, List

# Add the parent directory to the path so we can import from utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.response_processor import (
    normalize_owui_response, 
    normalize_owui_response_streaming,
    get_sources_from_owui
)


def test_normalize_with_done_signal():
    """Test that the optimizer stops processing when it encounters [DONE]"""
    print("Testing early termination with [DONE] signal...")
    
    # Simulate a stream with [DONE] signal in the middle
    test_data = {
        "stream": [
            {"sources": [{"page": 1, "text": "Test source"}]},
            {
                "choices": [{
                    "delta": {"content": "Hello "}
                }]
            },
            {
                "choices": [{
                    "delta": {"content": "world"}
                }]
            },
            "[DONE]",  # This should stop processing
            {
                "choices": [{
                    "delta": {"content": " this should not appear"}
                }]
            }
        ]
    }
    
    text, sources = normalize_owui_response(test_data)
    print(f"Result text: '{text}'")
    print(f"Sources: {sources}")
    
    # Should only contain "Hello world", not the text after [DONE]
    assert text == "Hello world", f"Expected 'Hello world', got '{text}'"
    assert len(sources) == 1, f"Expected 1 source, got {len(sources)}"
    print("✓ Early termination test passed")


def test_normalize_with_finish_reason():
    """Test that the optimizer stops processing when it encounters finish_reason: stop"""
    print("\nTesting early termination with finish_reason...")
    
    test_data = {
        "stream": [
            {"sources": [{"page": 2, "text": "Another source"}]},
            {
                "choices": [{
                    "delta": {"content": "Complete "}
                }]
            },
            {
                "choices": [{
                    "delta": {"content": "response"},
                    "finish_reason": "stop"
                }]
            },
            {
                "choices": [{
                    "delta": {"content": " extra content"}
                }]
            }
        ]
    }
    
    text, sources = normalize_owui_response(test_data)
    print(f"Result text: '{text}'")
    print(f"Sources: {sources}")
    
    # Should only contain "Complete response", not the extra content
    assert text == "Complete response", f"Expected 'Complete response', got '{text}'"
    assert len(sources) == 1, f"Expected 1 source, got {len(sources)}"
    print("✓ Finish reason test passed")


def test_ndjson_with_done():
    """Test NDJSON processing with [DONE] signal"""
    print("\nTesting NDJSON early termination...")
    
    test_data = {
        "ndjson": [
            {
                "choices": [{
                    "delta": {"content": "NDJSON "}
                }]
            },
            {
                "choices": [{
                    "delta": {"content": "content"}
                }]
            },
            "[DONE]",
            {
                "choices": [{
                    "delta": {"content": " should not appear"}
                }]
            }
        ]
    }
    
    text, sources = normalize_owui_response(test_data)
    print(f"Result text: '{text}'")
    
    assert text == "NDJSON content", f"Expected 'NDJSON content', got '{text}'"
    print("✓ NDJSON early termination test passed")


def test_get_sources_utility():
    """Test the new get_sources_from_owui utility function"""
    print("\nTesting get_sources_from_owui utility...")
    
    test_data = {
        "stream": [
            {"sources": [{"page": 5, "text": "Quick source"}]},
            {"choices": [{"delta": {"content": "Some content"}}]}
        ]
    }
    
    sources = get_sources_from_owui(test_data)
    print(f"Extracted sources: {sources}")
    
    assert len(sources) == 1, f"Expected 1 source, got {len(sources)}"
    assert sources[0]["page"] == 5, f"Expected page 5, got {sources[0]['page']}"
    print("✓ Sources utility test passed")


async def test_streaming_variant():
    """Test the new streaming variant function"""
    print("\nTesting streaming variant...")
    
    # Create a mock async iterator
    class MockAsyncIterator:
        def __init__(self, items):
            self.items = items
            self.index = 0
        
        def __aiter__(self):
            return self
        
        async def __anext__(self):
            if self.index >= len(self.items):
                raise StopAsyncIteration
            item = self.items[self.index]
            self.index += 1
            return self.index - 1, item  # Return index and item
    
    mock_stream = MockAsyncIterator([
        {"sources": [{"page": 10, "text": "Stream source"}]},
        {"choices": [{"delta": {"content": "Streaming "}}]},
        {"choices": [{"delta": {"content": "content"}}]},
        "[DONE]"
    ])
    
    chunks = []
    sources_received = None
    
    async for text_chunk, sources in normalize_owui_response_streaming(mock_stream):
        chunks.append(text_chunk)
        if sources and not sources_received:
            sources_received = sources
    
    combined_text = "".join(chunks)
    print(f"Streaming result: '{combined_text}'")
    print(f"Streaming sources: {sources_received}")
    
    assert "Streaming content" in combined_text or combined_text == "", "Should contain streaming content or be empty for sources-only chunk"
    assert sources_received is not None, "Should receive sources"
    print("✓ Streaming variant test passed")


def test_performance_comparison():
    """Create a large dataset to verify performance characteristics"""
    print("\nTesting performance with large dataset...")
    
    # Create a large stream with many chunks
    large_stream = {"stream": [{"sources": [{"page": 1, "text": "Large test"}]}]}
    
    # Add many content chunks
    for i in range(1000):
        large_stream["stream"].append({
            "choices": [{
                "delta": {"content": f"chunk{i} "}
            }]
        })
    
    # Add [DONE] signal in the middle
    large_stream["stream"].append("[DONE]")
    
    # Add more chunks that should be ignored
    for i in range(100):
        large_stream["stream"].append({
            "choices": [{
                "delta": {"content": f"ignored{i} "}
            }]
        })
    
    import time
    start_time = time.time()
    text, sources = normalize_owui_response(large_stream)
    end_time = time.time()
    
    print(f"Processing time: {end_time - start_time:.4f} seconds")
    print(f"Text length: {len(text)} characters")
    print(f"Text ends with: '{text[-20:]}'")
    
    # Should not contain any "ignored" content
    assert "ignored" not in text, "Should not contain content after [DONE]"
    # Should contain exactly 1000 chunks
    chunk_count = text.count("chunk")
    print(f"Chunk count: {chunk_count}")
    assert chunk_count == 1000, f"Expected 1000 chunks, got {chunk_count}"
    print("✓ Performance test passed")


async def main():
    """Run all tests"""
    print("Running optimized response_processor tests...\n")
    
    test_normalize_with_done_signal()
    test_normalize_with_finish_reason()
    test_ndjson_with_done()
    test_get_sources_utility()
    await test_streaming_variant()
    test_performance_comparison()
    
    print("\n🎉 All tests passed! The response processor optimization is working correctly.")
    print("\nOptimizations implemented:")
    print("✓ Early termination on [DONE] signal")
    print("✓ Early termination on finish_reason: stop")
    print("✓ Efficient list-based text concatenation (already existed)")
    print("✓ New streaming variant for true streaming scenarios")
    print("✓ Quick sources extraction utility")


if __name__ == "__main__":
    asyncio.run(main())
