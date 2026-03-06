#!/usr/bin/env python3
"""
Script to load metric data to OpenSearch for integration testing.

For each UUID in metadata_data.json, this script creates 50 metric documents
with timestamps spaced 30 seconds apart and loads them into OpenSearch.
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Error: requests library is required. Install it with: pip install requests")
    sys.exit(1)


def parse_es_server(es_server: str) -> tuple:
    """Parse ES_SERVER URL to extract base URL and credentials."""
    parsed = urlparse(es_server)
    base_url = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base_url += f":{parsed.port}"

    auth = None
    if parsed.username and parsed.password:
        auth = (parsed.username, parsed.password)

    return base_url, auth


def load_json_file(filepath: str) -> Any:
    """Load and parse a JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}")
        sys.exit(1)


def create_metric_documents(
    metric_template: Dict[str, Any],
    uuid: str,
    ocp_version: str,
    base_timestamp: datetime,
    count: int = 50,
    interval_seconds: int = 30
) -> List[Dict[str, Any]]:
    """
    Create multiple metric documents for a given UUID.

    Args:
        metric_template: Template metric document
        uuid: UUID to use for the documents
        ocp_version: OCP version to use in metadata
        base_timestamp: Starting timestamp
        count: Number of documents to create
        interval_seconds: Seconds between each document timestamp

    Returns:
        List of metric documents
    """
    documents = []

    for i in range(count):
        # Create a copy of the template
        doc = json.loads(json.dumps(metric_template))  # Deep copy

        # Replace UUID
        doc['uuid'] = uuid

        # Update timestamp (30 seconds apart)
        timestamp = base_timestamp + timedelta(seconds=i * interval_seconds)
        doc['timestamp'] = timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        # Update ocpVersion in metadata if it exists
        if 'metadata' in doc and isinstance(doc['metadata'], dict):
            doc['metadata']['ocpVersion'] = ocp_version
            # Extract major version if possible
            if ocp_version:
                if '.' in ocp_version:
                    major_version = ocp_version.split('.')[0] + '.' + ocp_version.split('.')[1]
                else:
                    major_version = ocp_version.split('.')[0]
                doc['metadata']['ocpMajorVersion'] = major_version

        documents.append(doc)

    return documents


def post_document(
    base_url: str,
    index: str,
    document: Dict[str, Any],
    auth: tuple = None,
    verify_ssl: bool = False,
    doc_id: Optional[str] = None
) -> tuple:
    """
    Post a single document to OpenSearch.

    Args:
        doc_id: Optional document ID. When provided, used for the _doc URL.
                When not provided, ID is derived from uuid+timestamp if present.

    Returns:
        (success, http_code, response_text)
    """
    url = f"{base_url}/{index}/_doc"

    if doc_id is not None:
        url = f"{base_url}/{index}/_doc/{doc_id}"
    elif 'uuid' in document and 'timestamp' in document:
        # Use UUID + timestamp as document ID to ensure uniqueness
        timestamp_id = document['timestamp'].replace(':', '').replace(
            '.', '').replace('-', '').replace('T', '').replace('Z', '')
        url = f"{base_url}/{index}/_doc/{document['uuid']}-{timestamp_id}"

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(
            url,
            json=document,
            headers=headers,
            auth=auth,
            verify=verify_ssl,
            timeout=30
        )

        success = response.status_code in (200, 201)
        return success, response.status_code, response.text
    except requests.exceptions.RequestException as e:
        return False, 0, str(e)


def ensure_index_exists(
    base_url: str,
    index: str,
    auth: tuple = None,
    verify_ssl: bool = False
) -> bool:
    """Check if index exists, create it if it doesn't."""
    url = f"{base_url}/{index}"
    headers = {'Content-Type': 'application/json'}

    # Check if index exists
    try:
        response = requests.head(
            url,
            auth=auth,
            verify=verify_ssl,
            timeout=10
        )
        if response.status_code == 200:
            return True
    except requests.exceptions.RequestException:
        pass

    # Create index
    try:
        response = requests.put(
            url,
            json={
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                }
            },
            headers=headers,
            auth=auth,
            verify=verify_ssl,
            timeout=10
        )
        return response.status_code in (200, 201)
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not create index: {e}")
        return False


def load_metadata_to_index(
    base_url: str,
    index: str,
    metadata_list: List[Dict[str, Any]],
    auth: tuple = None,
    verify_ssl: bool = False
) -> tuple:
    """
    Ensure the metadata index exists and post each metadata document to it.
    Uses document's 'uuid' as the OpenSearch document ID.

    Returns:
        (success_count, fail_count)
    """
    if not ensure_index_exists(base_url, index, auth, verify_ssl):
        print(f"Warning: Index '{index}' creation may have failed, continuing...")

    success_count = 0
    fail_count = 0

    for idx, doc in enumerate(metadata_list):
        uuid = doc.get('uuid')
        if not uuid:
            print(f"  [{idx + 1}/{len(metadata_list)}] Warning: no UUID, skipping")
            fail_count += 1
            continue

        success, http_code, response_text = post_document(
            base_url,
            index,
            doc,
            auth=auth,
            verify_ssl=verify_ssl,
            doc_id=uuid
        )

        if success:
            success_count += 1
            print(f"  [{idx + 1}/{len(metadata_list)}] ✓ Loaded UUID: {uuid}")
        else:
            fail_count += 1
            print(f"  [{idx + 1}/{len(metadata_list)}] ✗ Failed (HTTP {http_code})")
            if http_code != 0:
                print(f"    Response: {response_text[:200]}")

    return success_count, fail_count


def _run_rhoso_flow(args, base_url: str, auth: tuple) -> None:
    """Load rhoso.json: metadata to metadata index, metrics to metrics index."""
    print(f"OpenSearch server: {base_url}")
    print(f"Rhoso file: {args.rhoso_file}")
    print(f"Metadata index: {args.metadata_index}")
    print(f"Metrics index: {args.index}")
    print("\n")

    print("Loading rhoso file...")
    data = load_json_file(args.rhoso_file)
    if not isinstance(data, dict) or 'metadata' not in data or 'metrics' not in data:
        print("Error: rhoso file must be a JSON object with 'metadata' and 'metrics' keys")
        sys.exit(1)
    metadata_list = data['metadata']
    metrics_list = data['metrics']
    if not isinstance(metadata_list, list) or not isinstance(metrics_list, list):
        print("Error: 'metadata' and 'metrics' must be JSON arrays")
        sys.exit(1)
    print(f"Found {len(metadata_list)} metadata documents and {len(metrics_list)} metric documents")
    print("\n")

    print(f"Testing connection to OpenSearch at {base_url}...")
    try:
        response = requests.get(base_url, auth=auth, verify=args.verify_ssl, timeout=10)
        if response.status_code == 200:
            print("✓ Connection successful")
        else:
            print(f"Warning: Unexpected response: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not connect to OpenSearch: {e}")
        print("Continuing anyway...")
    print("\n")

    # Load metadata to metadata index
    print(f"Loading metadata to index '{args.metadata_index}'...")
    meta_success, meta_fail = load_metadata_to_index(
        base_url, args.metadata_index, metadata_list, auth, args.verify_ssl
    )
    print("\n")

    # Load metrics to metrics index
    print(f"Loading metrics to index '{args.index}'...")
    if not ensure_index_exists(base_url, args.index, auth, args.verify_ssl):
        print("Warning: Index creation may have failed, continuing...")
    print("")

    metrics_success = 0
    metrics_fail = 0
    for idx, doc in enumerate(metrics_list):
        uuid_val = doc.get('browbeat_uuid', doc.get('uuid', ''))
        ts = doc.get('timestamp', '')
        ts_norm = ts.replace(':', '').replace('.', '')\
            .replace('-', '').replace('T', '').replace('Z', '')[:-3]
        doc_id = f"{uuid_val}-{ts_norm}-{doc.get('iteration', 0)}"

        success, http_code, response_text = post_document(
            base_url,
            args.index,
            doc,
            auth=auth,
            verify_ssl=args.verify_ssl,
            doc_id=doc_id
        )
        if success:
            metrics_success += 1
            if (idx + 1) % 10 == 0 or idx == len(metrics_list) - 1:
                print(f"  [{idx + 1}/{len(metrics_list)}] ✓ Loaded")
        else:
            metrics_fail += 1
            print(f"  [{idx + 1}/{len(metrics_list)}] ✗ Failed (HTTP {http_code})")
            if http_code != 0:
                print(f"    Response: {response_text[:200]}")
    print("\n")

    # Summary
    total_success = meta_success + metrics_success
    total_fail = meta_fail + metrics_fail
    total_docs = len(metadata_list) + len(metrics_list)
    print("=" * 50)
    print("Summary:")
    print(f"  Metadata: {meta_success} loaded, {meta_fail} failed")
    print(f"  Metrics:  {metrics_success} loaded, {metrics_fail} failed")
    print(f"  Total successfully loaded: {total_success} documents")
    print(f"  Total failed: {total_fail} documents")
    print(f"  Total: {total_docs} documents")
    print("=" * 50)

    if total_fail > 0:
        sys.exit(1)
    print("\n✓ All documents loaded successfully!")


def main():
    """Main function to load metric data to OpenSearch."""
    parser = argparse.ArgumentParser(
        description='Load metric data to OpenSearch for integration testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use defaults (localhost:9200, index: orion-integration-test-metrics)
  python load_metrics_to_opensearch.py

  # Custom OpenSearch server and index
  python load_metrics_to_opensearch.py \\
    --es-server https://opensearch.example.com:9200 \\
    --index my-metrics-index

  # With authentication
  export ES_SERVER="https://user:pass@opensearch.example.com:9200"
  python load_metrics_to_opensearch.py

  # Load rhoso.json (metadata -> orion-integration-test-data, metrics -> orion-integration-test-metrics)
  python load_metrics_to_opensearch.py --rhoso
        """
    )

    parser.add_argument(
        '--rhoso',
        action='store_true',
        help='Load rhoso.json: metadata to orion-integration-test-data,\
metrics to orion-integration-test-metrics (default: ./rhoso.json)'
    )
    parser.add_argument(
        '--rhoso-file',
        default=os.path.join(os.path.dirname(__file__), 'rhoso.json'),
        help='Path to rhoso JSON file when using --rhoso (default: ./rhoso.json)'
    )
    parser.add_argument(
        '--metadata-index',
        default='orion-integration-test-data',
        help='Index for metadata when using --rhoso (default: orion-integration-test-data)'
    )
    parser.add_argument(
        '--es-server',
        default=os.getenv('ES_SERVER', 'https://localhost:9200'),
        help='OpenSearch server URL (default: https://localhost:9200 or ES_SERVER env var)'
    )
    parser.add_argument(
        '--index',
        default='orion-integration-test-metrics',
        help='Index name for metrics (default: orion-integration-test-metrics;\
used for template mode and for --rhoso metrics)'
    )
    parser.add_argument(
        '--metadata-file',
        default=os.path.join(os.path.dirname(__file__), 'metadata_data.json'),
        help='Path to metadata JSON file (default: ./metadata_data.json)'
    )
    parser.add_argument(
        '--metric-file',
        default=os.path.join(os.path.dirname(__file__), 'metric_data.json'),
        help='Path to metric template JSON file (default: ./metric_data.json)'
    )
    parser.add_argument(
        '--count',
        type=int,
        default=50,
        help='Number of metric documents to create per UUID (default: 50)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=30,
        help='Seconds between timestamps (default: 30)'
    )
    parser.add_argument(
        '--verify-ssl',
        action='store_true',
        default=False,
        help='Verify SSL certificates (default: False)'
    )

    args = parser.parse_args()

    # Parse ES server URL
    base_url, auth = parse_es_server(args.es_server)

    if args.rhoso:
        _run_rhoso_flow(args, base_url, auth)
        return

    # Template mode (original flow)
    print(f"OpenSearch server: {base_url}")
    print(f"Index: {args.index}")
    print(f"Metadata file: {args.metadata_file}")
    print(f"Metric template file: {args.metric_file}")
    print(f"Documents per UUID: {args.count}")
    print(f"Timestamp interval: {args.interval} seconds")
    print("\n")

    # Load files
    print("Loading files...")
    metadata_list = load_json_file(args.metadata_file)
    metric_template = load_json_file(args.metric_file)

    if not isinstance(metadata_list, list):
        print("Error: metadata_data.json must contain a JSON array")
        sys.exit(1)

    print(f"Found {len(metadata_list)} UUIDs in metadata file")
    print("\n")

    # Test connection
    print(f"Testing connection to OpenSearch at {base_url}...")
    try:
        response = requests.get(base_url, auth=auth, verify=args.verify_ssl, timeout=10)
        if response.status_code == 200:
            print("✓ Connection successful")
        else:
            print(f"Warning: Unexpected response: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not connect to OpenSearch: {e}")
        print("Continuing anyway...")

    print("\n")

    # Ensure index exists
    print(f"Ensuring index '{args.index}' exists...")
    if ensure_index_exists(base_url, args.index, auth, args.verify_ssl):
        print("✓ Index ready")
    else:
        print("Warning: Index creation may have failed, but continuing...")

    print("\n")

    # Process each UUID
    total_docs = len(metadata_list) * args.count
    print(f"Generating and loading {total_docs} metric documents...")
    print("\n")

    success_count = 0
    fail_count = 0

    for metadata_idx, metadata in enumerate(metadata_list):
        uuid = metadata.get('uuid')
        ocp_version = metadata.get('ocpVersion', '')
        execution_date = metadata.get('executionDate', metadata.get('timestamp', ''))

        if not uuid:
            print(f"Warning: Entry {metadata_idx + 1} has no UUID, skipping...")
            continue

        # Parse base timestamp from executionDate or use current time
        try:
            if execution_date:
                # Remove 'Z' and parse
                base_ts_str = execution_date.replace('Z', '+00:00')
                base_timestamp = datetime.fromisoformat(base_ts_str)
                # Start 30 seconds after execution date
                base_timestamp += timedelta(seconds=30)
            else:
                base_timestamp = datetime.utcnow()
        except (ValueError, AttributeError):
            base_timestamp = datetime.utcnow()

        # Create metric documents for this UUID
        documents = create_metric_documents(
            metric_template,
            uuid,
            ocp_version,
            base_timestamp,
            args.count,
            args.interval
        )

        if uuid == "d4e5f6a7-b8c9-4012-d345-e6f7a8b9c012":
            for doc_idx, doc in enumerate(documents):
                documents[doc_idx]['value'] = 6.5699015877283817
        if uuid == "c3d4e5f6-a7b8-4901-c234-d5e6f7a8b901":
            for doc_idx, doc in enumerate(documents):
                documents[doc_idx]['value'] = 7.85699015877283817
        if uuid == "b2c3d4e5-f6a7-4890-b123-c4d5e6f7a890":
            for doc_idx, doc in enumerate(documents):
                documents[doc_idx]['value'] = 8.0199015877283817
        if uuid == "a1b2c3d4-e5f6-4789-a012-b3c4d5e6f789":
            for doc_idx, doc in enumerate(documents):
                documents[doc_idx]['value'] = 9.2369015877283817

        # Load documents
        print(f"UUID {metadata_idx + 1}/{len(metadata_list)}: {uuid}")
        for doc_idx, doc in enumerate(documents):
            success, http_code, response_text = post_document(
                base_url,
                args.index,
                doc,
                auth,
                args.verify_ssl
            )

            if success:
                success_count += 1
                if (doc_idx + 1) % 10 == 0 or doc_idx == len(documents) - 1:
                    print(f"  [{doc_idx + 1}/{args.count}] ✓ Loaded")
            else:
                fail_count += 1
                print(f"  [{doc_idx + 1}/{args.count}] ✗ Failed (HTTP {http_code})")
                if http_code != 0:
                    print(f"    Response: {response_text[:200]}")

        print("\n")

    # Summary
    print("=" * 50)
    print("Summary:")
    print(f"  Successfully loaded: {success_count} documents")
    print(f"  Failed: {fail_count} documents")
    print(f"  Total: {total_docs} documents")
    print("=" * 50)

    if fail_count > 0:
        sys.exit(1)

    print("\n✓ All documents loaded successfully!")


if __name__ == '__main__':
    main()
