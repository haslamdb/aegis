# Setup Guide

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/asp-bacteremia-alerts.git
cd asp-bacteremia-alerts
```

### 2. Start HAPI FHIR Server

```bash
docker compose up -d
```

This starts a local HAPI FHIR R4 server on port 8081.

Verify it's running:
```bash
curl http://localhost:8081/fhir/metadata | head -20
```

### 3. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.template .env
```

For local development, the defaults work out of the box.

### 5. Load Test Data

```bash
python -m src.setup_test_data
```

This creates 10 test patients with various bacteremia scenarios.

### 6. Run the Monitor

Single check:
```bash
python -m src.monitor
```

Continuous monitoring:
```bash
python -m src.monitor --continuous
```

### 7. Run Tests

```bash
pytest tests/ -v
```

## Test Scenarios

The setup script creates these test cases:

| # | Patient | Organism | Antibiotic | Expected |
|---|---------|----------|------------|----------|
| 1 | Alice Johnson | MRSA | Cefazolin | ALERT |
| 2 | Bob Smith | MRSA | Vancomycin | OK |
| 3 | Carol Davis | Pseudomonas | Ceftriaxone | ALERT |
| 4 | David Wilson | Pseudomonas | Cefepime | OK |
| 5 | Eve Brown | E. coli | Pip-tazo | OK |
| 6 | Frank Miller | Candida | Vanc + Cefepime | ALERT |
| 7 | Grace Taylor | VRE | Vancomycin | ALERT |
| 8 | Henry White | GPC clusters | Cefazolin | ALERT |
| 9 | Irene Martinez | Klebsiella | Ceftriaxone | OK |
| 10 | Jack Lee | E. coli | None | ALERT |

## Docker Commands

```bash
# Start HAPI FHIR
docker compose up -d

# View logs
docker compose logs -f hapi-fhir

# Stop
docker compose down

# Stop and remove data
docker compose down -v
```

## Production Setup (Epic FHIR)

### 1. Obtain Epic Credentials

Work with your IT department to:
1. Register a backend application in Epic App Orchard
2. Generate an RSA key pair
3. Get your Client ID
4. Configure allowed FHIR scopes

### 2. Configure Keys

Place your private key in the `keys/` directory:
```bash
mkdir -p keys
cp /path/to/your/private_key.pem keys/epic_private.pem
chmod 600 keys/epic_private.pem
```

### 3. Update Environment

Edit `.env`:
```bash
EPIC_FHIR_BASE_URL=https://epicfhir.your-hospital.org/api/FHIR/R4
EPIC_CLIENT_ID=your-client-id-from-epic
EPIC_PRIVATE_KEY_PATH=./keys/epic_private.pem
```

### 4. Test Connection

```bash
python -c "from src.fhir_client import get_fhir_client; c = get_fhir_client(); print(c.get('metadata')['software'])"
```

## Troubleshooting

### HAPI FHIR won't start

Check if port 8081 is in use:
```bash
ss -tlnp | grep 8081
```

Change the port in `docker-compose.yml` if needed.

### No blood cultures found

The date filter may be too restrictive. Check that test data dates are within the lookback window:
```bash
curl "http://localhost:8081/fhir/DiagnosticReport?code=http://loinc.org|600-7"
```

### Epic authentication fails

1. Verify private key format (PEM, RSA)
2. Check Client ID matches Epic registration
3. Ensure token endpoint URL is correct
4. Verify required FHIR scopes are granted

### Tests fail

Ensure you're in the virtual environment:
```bash
source venv/bin/activate
pytest tests/ -v
```
