#!/usr/bin/env python3

import json
import requests
import sys
import os
import argparse
from typing import List, Dict, Any

default_opensearch_url = "http://localhost:9200"
default_opensearch_username = "admin"
default_opensearch_password = ""
default_index_name = "kube-burner-data"
default_data_type = "auto"

class OpenSearchBulkUploader:
    def __init__(self, opensearch_url, opensearch_username, opensearch_password,
                 opensearch_verify, index_name, data_type):
        self.opensearch_url = opensearch_url.rstrip('/')
        self.index_name = index_name
        self.data_type = data_type
        self.session = requests.Session()
        self.session.verify = opensearch_verify
        if opensearch_password:
            self.auth = requests.auth.HTTPBasicAuth(opensearch_username, opensearch_password)
        else:
            self.auth = None

    def get_data_type_from_records(self, records: List[Dict[Any, Any]]) -> str:
        """Auto-detect data type from records based on metricName"""
        if not records:
            return "unknown"

        sample_record = records[0]
        metric_name = sample_record.get("metricName", "").lower()

        if "dv" in metric_name or "datavolume" in metric_name:
            return "dv-latency"
        elif "vmi" in metric_name or "virtualmachine" in metric_name:
            return "vmi-latency"
        elif "pod" in metric_name:
            return "pod-latency"

        return "generic"

    def create_index_template(self) -> bool:
        """Create flexible index template that supports multiple data types"""
        # Base mappings that are common across all data types
        base_properties = {
            "@timestamp": {"type": "date"},
            "timestamp": {"type": "date"},
            "metricName": {"type": "keyword"},
            "uuid": {"type": "keyword"},
            "namespace": {"type": "keyword"},
            "jobName": {"type": "keyword"},
            "jobIteration": {"type": "keyword"},
            "replica": {"type": "keyword"},
            "source": {"type": "keyword"},
            "dataType": {"type": "keyword"},
            "organizationID": {"type": "keyword"},
            "metadata": {
                "type": "object",
                "properties": {
                    "ocpMajorVersion": {"type": "keyword"},
                    "ocpVersion": {"type": "keyword"}
                }
            }
        }

        # VMI-specific properties
        vmi_properties = {
            "podName": {"type": "keyword"},
            "vmName": {"type": "keyword"},
            "vmiName": {"type": "keyword"},
            "nodeName": {"type": "keyword"},
            "podCreatedLatency": {"type": "float"},
            "podReadyLatency": {"type": "float"},
            "podScheduledLatency": {"type": "float"},
            "podInitializedLatency": {"type": "float"},
            "podContainersReadyLatency": {"type": "float"},
            "vmiCreatedLatency": {"type": "float"},
            "vmiPendingLatency": {"type": "float"},
            "vmiSchedulingLatency": {"type": "float"},
            "vmiScheduledLatency": {"type": "float"},
            "vmiRunningLatency": {"type": "float"},
            "vmReadyLatency": {"type": "float"}
        }

        # DV-specific properties
        dv_properties = {
            "dvName": {"type": "keyword"},
            "dvBoundLatency": {"type": "float"},
            "dvRunningLatency": {"type": "float"},
            "dvReadyLatency": {"type": "float"}
        }

        # Combine all properties for a flexible template
        all_properties = {**base_properties, **vmi_properties, **dv_properties}

        template = {
            "index_patterns": [f"{self.index_name}*"],
            "template": {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                    "index.refresh_interval": "30s"
                },
                "mappings": {
                    "properties": all_properties
                }
            }
        }

        url = f"{self.opensearch_url}/_index_template/kube-burner-template"
        try:
            response = self.session.put(url, json=template, auth=self.auth)
            response.raise_for_status()
            print(f"✓ Index template created successfully")
            return True
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to create index template: {e}")
            return False

    def prepare_bulk_data(self, records: List[Dict[Any, Any]], organization_id: str = None) -> str:
        """Convert records to bulk API format and enrich data in single loop"""
        bulk_data = []

        # Auto-detect data type if not explicitly set
        detected_data_type = self.get_data_type_from_records(records) if self.data_type == "auto" else self.data_type

        for record in records:
            # Enrich with organizationID if provided
            if organization_id:
                record['organizationID'] = organization_id

            # Convert jobIteration from integer to zero-padded 4-digit string
            if "jobIteration" in record and isinstance(record["jobIteration"], int):
                record["jobIteration"] = f"{record['jobIteration']:04d}"

            # Convert replica from integer to zero-padded 4-digit string
            if "replica" in record and isinstance(record["replica"], int):
                record["replica"] = f"{record['replica']:04d}"

            # Add metadata fields
            record["source"] = "direct-api"
            record["dataType"] = detected_data_type

            # Use timestamp as @timestamp if available
            if "timestamp" in record:
                record["@timestamp"] = record["timestamp"]

            # Bulk API action - use data type specific index if needed
            index_suffix = f"-{detected_data_type}" if detected_data_type != "generic" else ""
            final_index_name = f"{self.index_name}{index_suffix}"
            action = {"index": {"_index": final_index_name}}
            bulk_data.append(json.dumps(action))
            bulk_data.append(json.dumps(record))

        return "\n".join(bulk_data) + "\n"

    def bulk_upload(self, bulk_data: str) -> bool:
        """Upload data using bulk API"""
        url = f"{self.opensearch_url}/_bulk"
        headers = {"Content-Type": "application/x-ndjson"}

        try:
            response = self.session.post(url, data=bulk_data, headers=headers, auth=self.auth)
            response.raise_for_status()

            result = response.json()
            if result.get("errors"):
                print("✗ Bulk upload had errors:")
                for item in result.get("items", []):
                    if "index" in item and "error" in item["index"]:
                        print(f"  - {item['index']['error']}")
                return False
            else:
                print(f"✓ Successfully uploaded {len(result.get('items', []))} documents")
                return True

        except requests.exceptions.RequestException as e:
            print(f"✗ Bulk upload failed: {e}")
            return False

    def upload_json_file(self, file_path: str, organization_id: str = None) -> bool:
        """Upload JSON file to OpenSearch"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Handle both single objects and arrays
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                print(f"✗ Invalid JSON format in {file_path}")
                return False


            bulk_data = self.prepare_bulk_data(data, organization_id)
            return self.bulk_upload(bulk_data)

        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"✗ Error reading {file_path}: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(
        description="Push JSON data to OpenSearch using bulk API with support for multiple data types",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect data type (default)
  python3 push-data.py sample_data.json

  # Explicitly specify DV latency data
  python3 push-data.py dvLatencyMeasurement-create-base-vm.json --data-type dvLatency

  # VMI latency data with custom index
  python3 push-data.py vmi_data.json --data-type vmiLatency --index my-vmi-data

  # Custom OpenSearch instance with SSL verification disabled
  python3 push-data.py data.json --url http://localhost:9200 --no-verify --org-id acme-corp

Environment Variables:
  OPENSEARCH_URL      Default OpenSearch URL
  OPENSEARCH_USER     Default OpenSearch username
  OPENSEARCH_PASSWORD Default OpenSearch password
  OPENSEARCH_INDEX    Default index name prefix
  DATA_TYPE          Default data type (auto, vmiLatency, dvLatency, podLatency, generic)
  ORGANIZATION_ID     Default organization ID
        """
    )

    parser.add_argument(
        "json_file",
        help="Path to JSON file to upload"
    )

    parser.add_argument(
        "--url",
        default=os.getenv("OPENSEARCH_URL", default_opensearch_url),
        help=f"OpenSearch URL (default: $OPENSEARCH_URL or {default_opensearch_url})"
    )

    parser.add_argument(
        "--username",
        default=os.getenv("OPENSEARCH_USER", default_opensearch_username),
        help=f"OpenSearch URL (default: $OPENSEARCH_USER or {default_opensearch_username})"
    )

    parser.add_argument(
        "--password",
        default=os.getenv("OPENSEARCH_PASSWORD", default_opensearch_password),
        help=f"OpenSearch URL (default: $OPENSEARCH_PASSWORD or {default_opensearch_password})"
    )

    parser.add_argument(
        "--no-verify",
        action="store_true",
        default=False,
        help="Disable SSL certificate verification (default: False)"
    )

    parser.add_argument(
        "--index",
        default=os.getenv("OPENSEARCH_INDEX", default_index_name),
        help=f"Index name prefix (default: $OPENSEARCH_INDEX or {default_index_name})"
    )

    parser.add_argument(
        "--data-type",
        default=os.getenv("DATA_TYPE", default_data_type),
        choices=["auto", "vmiLatency", "dvLatency", "podLatency", "generic"],
        help=f"Data type for processing and indexing (default: $DATA_TYPE or {default_data_type})"
    )

    parser.add_argument(
        "--org-id",
        default=os.getenv("ORGANIZATION_ID"),
        help="Organization ID to add to each document (default: $ORGANIZATION_ID)"
    )

    args = parser.parse_args()

    uploader = OpenSearchBulkUploader(
        opensearch_url=args.url,
        opensearch_username=args.username,
        opensearch_password=args.password,
        opensearch_verify=not args.no_verify,
        index_name=args.index,
        data_type=args.data_type
    )

    print(f"📤 Uploading {args.json_file} to OpenSearch at {args.url}")
    print(f"📋 Index: {args.index}")
    print(f"🏷️  Data Type: {args.data_type}")
    if args.org_id:
        print(f"🏢 Organization ID: {args.org_id}")

    # Create index template first
    uploader.create_index_template()

    # Upload data
    success = uploader.upload_json_file(args.json_file, args.org_id)

    if success:
        print("🎉 Upload completed successfully!")
        sys.exit(0)
    else:
        print("❌ Upload failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()