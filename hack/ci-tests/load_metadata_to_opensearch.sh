#!/bin/bash

# Script to load metadata_data.json to OpenSearch as individual documents
# Usage: ./load_metadata_to_opensearch.sh [options]
#
# Options:
#   --es-server URL          OpenSearch server URL (default: https://localhost:9200)
#   --index NAME            Index name (default: orion-integration-test-data)
#   --file PATH             Path to JSON file (default: ./metadata_data.json)
#   --insecure              Skip SSL certificate verification
#   --help                  Show this help message
#
# Environment variables:
#   ES_SERVER               OpenSearch server URL with User and Password
#   ES_METADATA_INDEX       Index name for metadata

set -euo pipefail

# Default values
ES_SERVER="${ES_SERVER:-https://localhost:9200}"
INDEX_NAME="${ES_METADATA_INDEX:-orion-integration-test-data}"
JSON_FILE="${JSON_FILE:-$(dirname "$0")/metadata_data.json}"
INSECURE=true

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --es-server)
            ES_SERVER="$2"
            shift 2
            ;;
        --index)
            INDEX_NAME="$2"
            shift 2
            ;;
        --file)
            JSON_FILE="$2"
            shift 2
            ;;
        --insecure)
            INSECURE=true
            shift
            ;;
        --help)
            head -n 20 "$0" | grep -E '^#( |$)' | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Validate inputs
if [[ ! -f "$JSON_FILE" ]]; then
    echo "Error: JSON file not found: $JSON_FILE" >&2
    exit 1
fi

# Check if jq is available (for parsing JSON)
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed." >&2
    echo "Please install jq: brew install jq (macOS) or apt-get install jq (Linux)" >&2
    exit 1
fi

# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo "Error: curl is required but not installed." >&2
    exit 1
fi

# Build curl options
CURL_OPTS=(-s -w "\nHTTP_CODE:%{http_code}\n")
if [[ "$INSECURE" == "true" ]]; then
    CURL_OPTS+=(-k)
fi

# Test OpenSearch connection
echo "Testing connection to OpenSearch at $ES_SERVER..."
if ! curl "${CURL_OPTS[@]}" "$ES_SERVER" > /dev/null 2>&1; then
    echo "Warning: Could not connect to OpenSearch. Continuing anyway..." >&2
fi

# Check if index exists, create if it doesn't
echo "Checking if index '$INDEX_NAME' exists..."
INDEX_EXISTS=$(curl "${CURL_OPTS[@]}" -X HEAD "$ES_SERVER/$INDEX_NAME" 2>&1 | grep -o "HTTP_CODE:200" || echo "")

if [[ -z "$INDEX_EXISTS" ]]; then
    echo "Index '$INDEX_NAME' does not exist. Creating it..."
    CREATE_RESPONSE=$(curl "${CURL_OPTS[@]}" -X PUT "$ES_SERVER/$INDEX_NAME" \
        -H "Content-Type: application/json" \
        -d '{
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            }
        }' 2>&1)
    
    if echo "$CREATE_RESPONSE" | grep -q "HTTP_CODE:200\|HTTP_CODE:201"; then
        echo "Index created successfully."
    else
        echo "Warning: Failed to create index. Response: $CREATE_RESPONSE" >&2
        echo "Continuing anyway - OpenSearch may auto-create the index..." >&2
    fi
else
    echo "Index '$INDEX_NAME' already exists."
fi

# Count total documents
TOTAL_DOCS=$(jq 'length' "$JSON_FILE")
echo ""
echo "Loading $TOTAL_DOCS documents from $JSON_FILE to index '$INDEX_NAME'..."
echo ""

# Load each document
SUCCESS_COUNT=0
FAIL_COUNT=0

for i in $(seq 0 $((TOTAL_DOCS - 1))); do
    # Extract the document
    DOC=$(jq -c ".[$i]" "$JSON_FILE")
    
    # Extract UUID for document ID (if available)
    UUID=$(echo "$DOC" | jq -r '.uuid // empty')
    
    # Build the URL - use UUID as document ID if available, otherwise let OpenSearch generate one
    if [[ -n "$UUID" && "$UUID" != "null" ]]; then
        DOC_URL="$ES_SERVER/$INDEX_NAME/_doc/$UUID"
    else
        DOC_URL="$ES_SERVER/$INDEX_NAME/_doc"
    fi
    
    # Post the document
    RESPONSE=$(curl "${CURL_OPTS[@]}" -X POST "$DOC_URL" \
        -H "Content-Type: application/json" \
        -d "$DOC" 2>&1)
    
    HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
    
    if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" ]]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        if [[ -n "$UUID" && "$UUID" != "null" ]]; then
            echo "[$((i + 1))/$TOTAL_DOCS] ✓ Loaded document with UUID: $UUID"
        else
            DOC_ID=$(echo "$RESPONSE" | jq -r '._id // "unknown"' 2>/dev/null || echo "unknown")
            echo "[$((i + 1))/$TOTAL_DOCS] ✓ Loaded document with ID: $DOC_ID"
        fi
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[$((i + 1))/$TOTAL_DOCS] ✗ Failed to load document (HTTP $HTTP_CODE)"
        echo "Response: $RESPONSE" >&2
    fi
done

echo ""
echo "========================================="
echo "Summary:"
echo "  Successfully loaded: $SUCCESS_COUNT documents"
echo "  Failed: $FAIL_COUNT documents"
echo "  Total: $TOTAL_DOCS documents"
echo "========================================="

if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
fi

exit 0
