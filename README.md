# Kube-Burner OpenSearch Visualization

This repository provides tools and configurations for visualizing [kube-burner-ocp](https://github.com/cloud-bulldozer/kube-burner-ocp) virtualization test results using OpenSearch and OpenSearch Dashboards.

## Overview

This project enables you to:
- Push kube-burner-ocp test results to OpenSearch
- Deploy OpenSearch and OpenSearch Dashboards on OpenShift
- Visualize VM/VMI and DataVolume latency metrics through pre-configured dashboards

## Repository Contents

```
.
├── feeder/
│   ├── push-data.py       # Python script to upload kube-burner data to OpenSearch
│   └── requirements.txt   # Python dependencies
├── deploy/
│   ├── opensearch-values.yml              # Helm values for OpenSearch
│   ├── opensearch-dashboard-value.yml     # Helm values for OpenSearch Dashboard
│   ├── opensearch-route.yml               # OpenShift route for OpenSearch
│   └── opensearch-dashboard-route.yml     # OpenShift route for OpenSearch Dashboard
└── opensearch-dashboards/
    └── vmLatency-opensearch-dashboard.ndjson  # Pre-configured dashboard
```

## Prerequisites

- **OpenShift Cluster**: Access to an OpenShift cluster with admin privileges
- **Helm 3**: For deploying OpenSearch and OpenSearch Dashboards
- **Python 3**: For running the data feeder script
- **kube-burner-ocp**: Test results in JSON format

## Configuration

Before deployment, you need to configure the OpenSearch values file:

### Edit `deploy/opensearch-values.yml`

Replace the placeholder values with your specific configuration:

1. **Storage Class** (`persistence.storageClass`): Set to your cluster's storage class
   - For OpenShift Container Storage (OCS): `ocs-storagecluster-ceph-rbd`
   - For AWS EBS: `gp2` or `gp3`
   - For other environments: Use `oc get storageclass` to find available options

2. **Admin Password** (`OPENSEARCH_INITIAL_ADMIN_PASSWORD`): Set a strong password
   - Must contain at least 8 characters
   - Should include uppercase, lowercase, numbers, and special characters
   - Example: `MySecureP@ssw0rd!2024`

Example configuration:
```yaml
config:
  opensearch.yml: |-
    cluster.name: opensearch-cluster
persistence:
  storageClass: ocs-storagecluster-ceph-rbd  # Change this to your storage class
extraEnvs:
- name: OPENSEARCH_INITIAL_ADMIN_PASSWORD
  value: "MySecureP@ssw0rd!2024"  # Change this to a strong password
```

## Deployment

### 1. Create Namespace

```bash
oc new-project burner-virt-results
```

### 2. Deploy OpenSearch

Add the OpenSearch Helm repository and install:

```bash
# Add OpenSearch Helm repository
helm repo add opensearch https://opensearch-project.github.io/helm-charts/
helm repo update

# Install OpenSearch
helm install opensearch opensearch/opensearch \
  -n burner-virt-results \
  -f deploy/opensearch-values.yml
```

Wait for OpenSearch to be ready:
```bash
oc get pods -n burner-virt-results -w
```

### 3. Create OpenSearch Route

```bash
oc apply -f deploy/opensearch-route.yml
```

Get the OpenSearch URL:
```bash
OPENSEARCH_URL=$(oc get route opensearch -n burner-virt-results -o jsonpath='{.spec.host}')
echo "OpenSearch URL: https://${OPENSEARCH_URL}"
```

### 4. Deploy OpenSearch Dashboard

```bash
# Install OpenSearch Dashboard
helm install burner-dashboard opensearch/opensearch-dashboards \
  -n burner-virt-results \
  -f deploy/opensearch-dashboard-value.yml
```

### 5. Create OpenSearch Dashboard Route

```bash
oc apply -f deploy/opensearch-dashboard-route.yml
```

Get the Dashboard URL:
```bash
DASHBOARD_URL=$(oc get route dashboard -n burner-virt-results -o jsonpath='{.spec.host}')
echo "Dashboard URL: http://${DASHBOARD_URL}"
```

## Data Upload

### Install Python Dependencies

```bash
cd feeder
pip install -r requirements.txt
```

### Upload kube-burner Test Results

The `push-data.py` script supports automatic detection of data types (VMI latency, DV latency, Pod latency) and bulk upload to OpenSearch.

#### Basic Usage

```bash
python3 push-data.py <path-to-json-file> \
  --url https://${OPENSEARCH_URL} \
  --username admin \
  --password <YOUR_ADMIN_PASSWORD> \
  --no-verify
```

#### Advanced Usage Examples

**Auto-detect data type (default):**
```bash
python3 push-data.py vmiLatencyMeasurement.json \
  --url https://${OPENSEARCH_URL} \
  --username admin \
  --password MySecureP@ssw0rd!2024 \
  --no-verify
```

**Explicitly specify data type:**
```bash
python3 push-data.py dvLatencyMeasurement.json \
  --url https://${OPENSEARCH_URL} \
  --username admin \
  --password MySecureP@ssw0rd!2024 \
  --data-type dvLatency \
  --no-verify
```

**With organization ID:**
```bash
python3 push-data.py results.json \
  --url https://${OPENSEARCH_URL} \
  --username admin \
  --password MySecureP@ssw0rd!2024 \
  --org-id my-team \
  --no-verify
```

#### Environment Variables

You can also configure the script using environment variables:

```bash
export OPENSEARCH_URL="https://${OPENSEARCH_URL}"
export OPENSEARCH_USER="admin"
export OPENSEARCH_PASSWORD="MySecureP@ssw0rd!2024"
export OPENSEARCH_INDEX="kube-burner-data"
export ORGANIZATION_ID="my-team"

python3 push-data.py vmiLatencyMeasurement.json --no-verify
```

#### Command-Line Options

- `--url`: OpenSearch URL (default: `http://localhost:9200`)
- `--username`: OpenSearch username (default: `admin`)
- `--password`: OpenSearch password
- `--no-verify`: Disable SSL certificate verification
- `--index`: Index name prefix (default: `kube-burner-data`)
- `--data-type`: Data type (`auto`, `vmiLatency`, `dvLatency`, `podLatency`, `generic`)
- `--org-id`: Organization ID to add to documents

### Supported Data Types

The script automatically detects and handles:

1. **VMI Latency**: Virtual Machine Instance lifecycle metrics
   - Pod creation, scheduling, and readiness latencies
   - VMI lifecycle latencies (created, pending, scheduling, scheduled, running)
   - VM ready latency

2. **DV Latency**: DataVolume provisioning metrics
   - DV bound, running, and ready latencies

3. **Pod Latency**: Generic pod metrics
   - Standard pod lifecycle latencies

## Dashboard Import

### 1. Access OpenSearch Dashboard

Navigate to the Dashboard URL in your browser:
```
http://<dashboard-route-host>
```

Log in with:
- **Username**: `admin`
- **Password**: `<YOUR_ADMIN_PASSWORD>` (the one you set in opensearch-values.yml)

### 2. Create Index Pattern

Before importing the dashboard, create an index pattern:

1. Go to **Management** → **Index Patterns**
2. Click **Create index pattern**
3. Enter pattern: `kube-burner-data*`
4. Click **Next step**
5. Select **@timestamp** or **timestamp** as the time field
6. Click **Create index pattern**

### 3. Import Dashboard

1. Go to **Management** → **Saved Objects**
2. Click **Import**
3. Select the file: `opensearch-dashboards/vmLatency-opensearch-dashboard.ndjson`
4. If prompted about conflicts, choose to overwrite
5. Click **Import**

### 4. View Dashboard

1. Go to **Dashboard** from the left menu
2. Open **VM Ready Latency Quantiles Dashboard - OpenSearch**

### Dashboard Features

The dashboard includes comprehensive visualizations for:

#### VM/VMI Latency Analysis
- **Median, Average, Minimum, Maximum** latency charts by job iteration
- **Percentile table** (P25, P50, P75, P90, P95, P99) grouped by UUID
- Charts show `vmReadyLatency` metric across different aggregations

#### DataVolume (DV) Latency Analysis
- **Median, Average, Minimum, Maximum** DV ready latency charts
- **Percentile table** for DV metrics
- Charts show `dvReadyLatency` metric across different aggregations

#### Important Usage Notes

⚠️ **UUID Filtering Required**: The charts require UUID filtering to show meaningful data:
1. Click **Add Filter** in the filter bar
2. Select field: `uuid`
3. Choose a UUID value from your data
4. Apply the filter

The percentile tables show all UUIDs for comparison without filtering.

## Data Structure

### Index Naming Convention

The script creates indices based on data type:
- `kube-burner-data-vmi-latency`: VMI latency data
- `kube-burner-data-dv-latency`: DV latency data
- `kube-burner-data-pod-latency`: Pod latency data
- `kube-burner-data`: Generic data

### Common Fields

All documents include:
- `@timestamp`, `timestamp`: Event timestamp
- `uuid`: Unique test run identifier
- `metricName`: Type of metric
- `jobName`, `jobIteration`: Test job information
- `namespace`: Kubernetes namespace
- `dataType`: Detected data type
- `source`: Data source identifier
- `organizationID`: Optional organization identifier

### VMI-Specific Fields

- Pod metrics: `podCreatedLatency`, `podReadyLatency`, `podScheduledLatency`, etc.
- VMI metrics: `vmiCreatedLatency`, `vmiPendingLatency`, `vmiSchedulingLatency`, etc.
- VM metrics: `vmReadyLatency`
- Identifiers: `podName`, `vmName`, `vmiName`, `nodeName`

### DV-Specific Fields

- `dvBoundLatency`: Time for DV to bind
- `dvRunningLatency`: Time for DV to start running
- `dvReadyLatency`: Time for DV to be ready
- `dvName`: DataVolume name

## Troubleshooting

### OpenSearch Pod Not Starting

Check storage class availability:
```bash
oc get storageclass
```

Verify PVC status:
```bash
oc get pvc -n burner-virt-results
```

### Data Upload Fails

Check OpenSearch connectivity:
```bash
curl -k -u admin:<password> https://${OPENSEARCH_URL}/_cluster/health
```

Verify index creation:
```bash
curl -k -u admin:<password> https://${OPENSEARCH_URL}/_cat/indices?v
```

### Dashboard Not Loading

Check pod logs:
```bash
oc logs -n burner-virt-results deployment/burner-dashboard-opensearch-dashboards
```

Verify route is accessible:
```bash
curl -I http://$(oc get route dashboard -n burner-virt-results -o jsonpath='{.spec.host}')
```

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Related Projects

- [kube-burner-ocp](https://github.com/cloud-bulldozer/kube-burner-ocp): The test framework that generates the data
- [OpenSearch](https://opensearch.org/): Search and analytics engine
- [OpenSearch Dashboards](https://opensearch.org/docs/latest/dashboards/): Visualization platform

