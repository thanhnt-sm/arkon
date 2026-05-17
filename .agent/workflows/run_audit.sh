#!/bin/bash

# Security Audit Script for Arkon
# Focused on preventing data exfiltration and custom-coded tracking.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔍 Starting Automated Security Audit...${NC}"

# 1. Check Framework Telemetry
echo -e "\n${YELLOW}Checking Framework Telemetry...${NC}"
grep -r "NEXT_TELEMETRY_DISABLED" . --exclude-dir=node_modules | grep "=1" > /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] NEXT_TELEMETRY_DISABLED is enforced.${NC}"
else
    echo -e "${RED}[FAIL] NEXT_TELEMETRY_DISABLED not found or not set to 1!${NC}"
fi

# 2. Scan for Suspicious Network Patterns (Excluding internal API)
echo -e "\n${YELLOW}Scanning for Custom Network Calls (potential exfiltration)...${NC}"
# Find fetch/axios/requests/http calls that don't point to internal or whitelisted domains
# We exclude src/lib/api.ts as it is our central, audited API client.
SUSPICIOUS_CALLS=$(find . -maxdepth 4 -not -path '*/.*' -not -path './node_modules*' -not -path './frontend/node_modules*' -not -path './frontend/src/lib/api.ts' -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" \) -exec grep -Ei "(fetch\(|axios\.|requests\.|http\.client|urllib)" {} + | grep -Ev "(/api/|localhost|127\.0\.0\.1|arkon_internal|openai\.com|anthropic\.com|google\.com)")

if [ -z "$SUSPICIOUS_CALLS" ]; then
    echo -e "${GREEN}[PASS] No suspicious external network calls found.${NC}"
else
    echo -e "${RED}[WARNING] Suspicious network patterns detected (Review required):${NC}"
    echo "$SUSPICIOUS_CALLS"
fi

# 3. Scan for Custom Tracking/Analytics Patterns
echo -e "\n${YELLOW}Scanning for Custom Tracking/Analytics Logic...${NC}"
TRACKING_PATTERNS=$(find . -maxdepth 4 -not -path '*/.*' -not -path './node_modules*' -not -path './frontend/node_modules*' -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" \) -exec grep -Ei "(track\(|report\(|send\(|emit\(|capture\()" {} + | grep -Ei "(user|email|content|wiki|document|behavior)")

if [ -z "$TRACKING_PATTERNS" ]; then
    echo -e "${GREEN}[PASS] No obvious custom tracking logic found.${NC}"
else
    echo -e "${RED}[WARNING] Potential custom tracking logic detected:${NC}"
    echo "$TRACKING_PATTERNS"
fi

# 4. Check Container Hardening
echo -e "\n${YELLOW}Checking Infrastructure Hardening (docker-compose)...${NC}"
grep "read_only: true" docker-compose.yml > /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] read_only containers are configured.${NC}"
else
    echo -e "${RED}[FAIL] read_only: true missing in docker-compose.yml!${NC}"
fi

echo -e "\n${YELLOW}✅ Security Audit Complete.${NC}"
