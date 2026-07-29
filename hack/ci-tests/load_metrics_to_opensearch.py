#!/usr/bin/env python3
"""
Load test data to OpenSearch for integration testing.

Modes:
  (default)    Generate metric documents from a template and bulk-index them.
  --metadata   Bulk-index metadata documents from metadata_data.json.
  --rhoso      Load rhoso.json (metadata + metrics) into their respective indexes.
  --all        Run metadata, metrics, and rhoso loading in one invocation.
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
    """Create multiple metric documents for a given UUID."""
    documents = []

    for i in range(count):
        doc = json.loads(json.dumps(metric_template))

        doc['uuid'] = uuid

        timestamp = base_timestamp + timedelta(seconds=i * interval_seconds)
        doc['timestamp'] = timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        if 'metadata' in doc and isinstance(doc['metadata'], dict):
            doc['metadata']['ocpVersion'] = ocp_version
            if ocp_version:
                if '.' in ocp_version:
                    major_version = ocp_version.split('.')[0] + '.' + ocp_version.split('.')[1]
                else:
                    major_version = ocp_version.split('.')[0]
                doc['metadata']['ocpMajorVersion'] = major_version

        documents.append(doc)

    return documents


def _make_doc_id(document: Dict[str, Any], doc_id: Optional[str] = None) -> Optional[str]:
    """Derive a deterministic document ID."""
    if doc_id is not None:
        return doc_id
    if 'uuid' in document and 'timestamp' in document:
        timestamp_id = document['timestamp'].replace(':', '').replace(
            '.', '').replace('-', '').replace('T', '').replace('Z', '')
        return f"{document['uuid']}-{timestamp_id}"
    return None


def bulk_index(
    base_url: str,
    index: str,
    documents: List[Dict[str, Any]],
    auth: tuple = None,
    verify_ssl: bool = False,
    doc_ids: Optional[List[Optional[str]]] = None,
    batch_size: int = 500
) -> tuple:
    """
    Index documents using the OpenSearch _bulk API.

    Returns:
        (success_count, fail_count)
    """
    if doc_ids is None:
        doc_ids = [None] * len(documents)

    success_count = 0
    fail_count = 0

    for batch_start in range(0, len(documents), batch_size):
        batch_docs = documents[batch_start:batch_start + batch_size]
        batch_ids = doc_ids[batch_start:batch_start + batch_size]

        lines = []
        for doc, did in zip(batch_docs, batch_ids):
            resolved_id = _make_doc_id(doc, did)
            action = {"index": {"_index": index}}
            if resolved_id:
                action["index"]["_id"] = resolved_id
            lines.append(json.dumps(action))
            lines.append(json.dumps(doc))

        body = "\n".join(lines) + "\n"

        try:
            response = requests.post(
                f"{base_url}/_bulk",
                data=body,
                headers={"Content-Type": "application/x-ndjson"},
                auth=auth,
                verify=verify_ssl,
                timeout=60
            )

            if response.status_code not in (200, 201):
                print(f"  Bulk request failed with HTTP {response.status_code}")
                print(f"  Response: {response.text[:500]}")
                fail_count += len(batch_docs)
                continue

            result = response.json()
            for item in result.get("items", []):
                op = item.get("index") or item.get("create", {})
                if op.get("status") in (200, 201):
                    success_count += 1
                else:
                    fail_count += 1

        except requests.exceptions.RequestException as e:
            print(f"  Bulk request error: {e}")
            fail_count += len(batch_docs)

        print(f"  [{min(batch_start + batch_size, len(documents))}/{len(documents)}] bulk indexed")

    return success_count, fail_count


def ensure_index_exists(
    base_url: str,
    index: str,
    auth: tuple = None,
    verify_ssl: bool = False
) -> bool:
    """Check if index exists, create it if it doesn't."""
    url = f"{base_url}/{index}"
    headers = {'Content-Type': 'application/json'}

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
    print("=" * 50)
    print(f"Loading {len(metadata_list)} metadata documents to '{args.metadata_index}'...")
    print("=" * 50)

    if not ensure_index_exists(base_url, args.metadata_index, auth, args.verify_ssl):
        print(f"Warning: Index '{args.metadata_index}' creation may have failed, continuing...")

    metadata_ids = [doc.get('uuid') for doc in metadata_list]
    metadata_success, metadata_fail = bulk_index(
        base_url,
        args.metadata_index,
        metadata_list,
        auth=auth,
        verify_ssl=args.verify_ssl,
        doc_ids=metadata_ids
    )
    print("\n")

    # Load metrics to metrics index
    print("=" * 50)
    print(f"Loading {len(metrics_list)} metric documents to '{args.index}'...")
    print("=" * 50)

    if not ensure_index_exists(base_url, args.index, auth, args.verify_ssl):
        print(f"Warning: Index '{args.index}' creation may have failed, continuing...")

    metrics_ids = []
    for idx, doc in enumerate(metrics_list):
        browbeat_uuid = doc.get('browbeat_uuid')
        timestamp = doc.get('timestamp', '')
        iteration = doc.get('iteration', idx)
        if browbeat_uuid and timestamp:
            timestamp_id = timestamp.replace(':', '').replace(
                '.', '').replace('-', '').replace('T', '').replace('Z', '')
            metrics_ids.append(f"{browbeat_uuid}-{timestamp_id}-{iteration}")
        else:
            metrics_ids.append(None)

    metrics_success, metrics_fail = bulk_index(
        base_url,
        args.index,
        metrics_list,
        auth=auth,
        verify_ssl=args.verify_ssl,
        doc_ids=metrics_ids
    )
    print("\n")

    # Summary
    print("=" * 50)
    print("Summary:")
    print(f"  Metadata - Success: {metadata_success}, Failed: {metadata_fail}")
    print(f"  Metrics  - Success: {metrics_success}, Failed: {metrics_fail}")
    total_success = metadata_success + metrics_success
    total_fail = metadata_fail + metrics_fail
    print(f"  Total    - Success: {total_success}, Failed: {total_fail}")
    print("=" * 50)

    if metadata_fail > 0 or metrics_fail > 0:
        sys.exit(1)

    print("\n✓ All documents loaded successfully!")


def _run_metadata_flow(args, base_url: str, auth: tuple) -> None:
    """Load metadata_data.json into the metadata index."""
    print(f"OpenSearch server: {base_url}")
    print(f"Metadata index: {args.metadata_index}")
    print(f"Metadata file: {args.metadata_file}")
    print("\n")

    metadata_list = load_json_file(args.metadata_file)
    if not isinstance(metadata_list, list):
        print("Error: metadata file must contain a JSON array")
        sys.exit(1)

    print(f"Found {len(metadata_list)} metadata documents")

    if not ensure_index_exists(base_url, args.metadata_index, auth, args.verify_ssl):
        print(f"Warning: Index '{args.metadata_index}' creation may have failed, continuing...")

    doc_ids = [doc.get('uuid') for doc in metadata_list]
    success, fail = bulk_index(
        base_url,
        args.metadata_index,
        metadata_list,
        auth=auth,
        verify_ssl=args.verify_ssl,
        doc_ids=doc_ids
    )

    print(f"\nMetadata: {success} loaded, {fail} failed")
    if fail > 0:
        sys.exit(1)
    print("✓ Metadata loaded successfully!")


def _run_metrics_flow(args, base_url: str, auth: tuple) -> None:
    """Generate and load template-based metric documents."""
    metadata_list = load_json_file(args.metadata_file)
    metric_template = load_json_file(args.metric_file)

    if not isinstance(metadata_list, list):
        print("Error: metadata_data.json must contain a JSON array")
        sys.exit(1)

    if not ensure_index_exists(base_url, args.index, auth, args.verify_ssl):
        print("Warning: Index creation may have failed, but continuing...")

    all_documents = []
    for metadata in metadata_list:
        uuid = metadata.get('uuid')
        ocp_version = metadata.get('ocpVersion', '')
        execution_date = metadata.get('executionDate', metadata.get('timestamp', ''))

        if not uuid:
            continue

        try:
            if execution_date:
                base_ts_str = execution_date.replace('Z', '+00:00')
                base_timestamp = datetime.fromisoformat(base_ts_str)
                base_timestamp += timedelta(seconds=30)
            else:
                base_timestamp = datetime.utcnow()
        except (ValueError, AttributeError):
            base_timestamp = datetime.utcnow()

        documents = create_metric_documents(
            metric_template,
            uuid,
            ocp_version,
            base_timestamp,
            args.count,
            args.interval
        )

        if uuid == "d4e5f6a7-b8c9-4012-d345-e6f7a8b9c012":
            for doc in documents:
                doc['value'] = 6.5699015877283817
        if uuid == "c3d4e5f6-a7b8-4901-c234-d5e6f7a8b901":
            for doc in documents:
                doc['value'] = 7.85699015877283817
        if uuid == "b2c3d4e5-f6a7-4890-b123-c4d5e6f7a890":
            for doc in documents:
                doc['value'] = 8.0199015877283817
        if uuid == "a1b2c3d4-e5f6-4789-a012-b3c4d5e6f789":
            for doc in documents:
                doc['value'] = 9.2369015877283817

        all_documents.extend(documents)

    print(f"  Generated {len(all_documents)} metric documents")
    success, fail = bulk_index(
        base_url,
        args.index,
        all_documents,
        auth,
        args.verify_ssl
    )

    print(f"\nMetrics: {success} loaded, {fail} failed")
    if fail > 0:
        sys.exit(1)
    print("✓ Metrics loaded successfully!")


def _run_all(args, base_url: str, auth: tuple) -> None:
    """Load metadata, metrics, and rhoso data in one invocation."""
    print(f"OpenSearch server: {base_url}")
    print(f"Metadata index: {args.metadata_index}")
    print(f"Metrics index: {args.index}")
    print("")

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
    print("")

    print("=" * 50)
    print("Step 1/3: Loading metadata")
    print("=" * 50)
    _run_metadata_flow(args, base_url, auth)
    print("")

    print("=" * 50)
    print("Step 2/3: Loading metrics")
    print("=" * 50)
    _run_metrics_flow(args, base_url, auth)
    print("")

    print("=" * 50)
    print("Step 3/3: Loading rhoso data")
    print("=" * 50)
    _run_rhoso_flow(args, base_url, auth)
    print("")

    print("=" * 50)
    print("✓ All data loaded successfully!")
    print("=" * 50)


def main():
    """Main function to load test data to OpenSearch."""
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
        """
    )

    parser.add_argument(
        '--es-server',
        default=os.getenv('ES_SERVER', 'https://localhost:9200'),
        help='OpenSearch server URL (default: https://localhost:9200 or ES_SERVER env var)'
    )
    parser.add_argument(
        '--index',
        default='orion-integration-test-metrics',
        help='Index name for metrics (default: orion-integration-test-metrics)'
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
    parser.add_argument(
        '--rhoso',
        action='store_true',
        default=False,
        help='Load rhoso.json: metadata and metrics to default integration-test indices'
    )
    parser.add_argument(
        '--rhoso-file',
        default=os.path.join(os.path.dirname(__file__), 'rhoso.json'),
        help='Path to rhoso JSON file (used with --rhoso) (default: ./rhoso.json)'
    )
    parser.add_argument(
        '--metadata-index',
        default='orion-integration-test-data',
        help='Index name for metadata (default: orion-integration-test-data)'
    )
    parser.add_argument(
        '--metadata',
        action='store_true',
        default=False,
        help='Load metadata documents from metadata_data.json into the metadata index'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        default=False,
        help='Load metadata, metrics, and rhoso data in one invocation'
    )

    args = parser.parse_args()

    # Parse ES server URL
    base_url, auth = parse_es_server(args.es_server)

    # --all runs all three flows sequentially
    if args.all:
        _run_all(args, base_url, auth)
        return

    # Handle rhoso mode
    if args.rhoso:
        _run_rhoso_flow(args, base_url, auth)
        return

    # Handle metadata-only mode
    if args.metadata:
        _run_metadata_flow(args, base_url, auth)
        return

    # Default mode: generate and load metrics
    print(f"OpenSearch server: {base_url}")
    print(f"Metrics index: {args.index}")
    print("")
    _run_metrics_flow(args, base_url, auth)


if __name__ == '__main__':
    main()
