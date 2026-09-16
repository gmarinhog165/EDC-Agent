#!/usr/bin/env python3
"""
Stress-test seeder: creates 1000 assets across random domains, then a targeted
domain with 5 precisely-described assets for retrieval quality testing.

Usage:
  python3 seed_stress.py seed   [--host HOST] [--api-key KEY] [--workers N]
  python3 seed_stress.py clean  [--host HOST] [--api-key KEY] [--workers N]
  python3 seed_stress.py query  # print the suggested test query and expected IDs
"""

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MANIFEST_PATH = Path(__file__).parent / "stress_manifest.json"
DUMMY_URL = "https://jsonplaceholder.typicode.com/todos"
ACCESS_POLICY_ID = "tb-require-membership"
CONTRACT_POLICY_ID = "tb-require-dataprocessor"
ASSET_PREFIX = "stress-"
TOTAL_ASSETS = 1000

# ---------------------------------------------------------------------------
# Domain corpus — 18 broad domains, descriptions generated from templates.
# Each domain produces TOTAL_ASSETS / len(DOMAINS) noise assets.
# ---------------------------------------------------------------------------

DOMAINS: dict[str, dict] = {
    "fintech": {
        "subtopics": [
            "payment transaction logs with merchant category codes and fraud flags",
            "credit scoring model features derived from open banking data",
            "FX spot price time series for G10 currency pairs",
            "alternative lending repayment performance for SMEs",
            "CBDC pilot transaction records from sandbox environment",
            "real-time stock order book snapshots for equity markets",
            "KYC document verification outcomes and AML alert history",
            "insurance claims frequency and severity by policyholder segment",
            "crypto DeFi protocol liquidity pool depth data",
            "cross-border remittance corridor volume and fee benchmarks",
        ],
    },
    "healthcare": {
        "subtopics": [
            "anonymised ICU patient vital sign time series at 1-minute resolution",
            "genomic variant call format files for rare disease cohort",
            "electronic health record discharge summaries in HL7 FHIR format",
            "drug adverse event reports submitted to pharmacovigilance registry",
            "radiological image metadata and diagnostic codes for chest CT scans",
            "randomised controlled trial enrolment and endpoint data",
            "wearable biosensor streams from cardiac rehabilitation programme",
            "hospital bed occupancy and emergency department wait times",
            "antibiotic resistance surveillance across reference laboratories",
            "mental health survey responses and PHQ-9 scoring longitudinal data",
        ],
    },
    "logistics": {
        "subtopics": [
            "parcel scan events and carrier handover timestamps across last-mile network",
            "cold-chain temperature excursion logs for pharmaceutical shipments",
            "warehouse slot utilisation and pick path efficiency metrics",
            "intermodal container dwell times at Iberian seaports",
            "customs declaration processing latency and rejection codes",
            "truck telematics data including speed, idling, and fuel consumption",
            "demand forecast accuracy reports by SKU and distribution centre",
            "returns processing reason codes and restocking time by category",
            "carrier on-time delivery rate benchmarks per postal zone",
            "hazardous materials transport incident registry",
        ],
    },
    "real-estate": {
        "subtopics": [
            "residential property transaction prices at NUTS-3 level",
            "building energy performance certificate ratings and floor area",
            "short-term rental listing density and nightly price by neighbourhood",
            "commercial office vacancy rate and prime rent per city centre zone",
            "construction permit issuance volume and average approval time",
            "mortgage origination data by loan-to-value bucket",
            "land use classification raster from cadastral authority",
            "property flood risk exposure scores based on topographic modelling",
            "social housing waiting list duration by municipality",
            "real estate agent market share and average days on market",
        ],
    },
    "agriculture": {
        "subtopics": [
            "NDVI time series for irrigated farmland derived from Sentinel-2",
            "soil electrical conductivity field survey for precision fertilisation",
            "crop yield per hectare by variety and region from farm census",
            "pesticide application records with active substance and dosage",
            "weather station data for agrometeorological decision support",
            "animal traceability events from birth to slaughterhouse",
            "organic certification audit outcomes and non-conformity reports",
            "irrigation scheduling recommendations from soil-water-balance model",
            "food safety sampling results for fresh produce from wholesale markets",
            "aquifer recharge levels and groundwater abstraction licences",
        ],
    },
    "climate": {
        "subtopics": [
            "ERA5 reanalysis hourly 2-metre temperature gridded for Iberia",
            "CO2 flux measurements from eddy covariance towers in boreal forest",
            "sea surface temperature anomaly maps from AVHRR satellite",
            "extreme precipitation event catalogue with return period estimates",
            "glacier mass balance measurements from in-situ field surveys",
            "urban heat island intensity index across 50 European cities",
            "atmospheric aerosol optical depth from AERONET sun photometers",
            "forest fire burned area perimeters and severity scores",
            "drought index (SPI-12) monthly maps for Mediterranean region",
            "phenological transition dates derived from satellite vegetation data",
        ],
    },
    "sports": {
        "subtopics": [
            "football match event sequences with player tracking coordinates",
            "cycling power meter and heart rate data from grand tour stages",
            "tennis serve speed and placement distribution per set",
            "swimming race split times and stroke rate at national championships",
            "athlete injury incidence and return-to-play duration by sport",
            "stadium attendance and ticketing revenue by fixture and tier",
            "eSports tournament match metadata and in-game economy statistics",
            "sports betting odds movement and settlement records",
            "youth academy scouting assessment scores and progression tracking",
            "sports nutrition supplement usage survey from professional athletes",
        ],
    },
    "ecommerce": {
        "subtopics": [
            "product catalogue with embedding vectors for visual similarity search",
            "A/B test conversion rate results for checkout funnel variants",
            "customer lifetime value cohort analysis by acquisition channel",
            "return reason codes and refund processing time by category",
            "marketplace seller performance scorecard and policy violation flags",
            "recommendation engine click-through and add-to-cart lift data",
            "inventory stockout events and lost-sales estimate by warehouse",
            "delivery experience survey NPS scores linked to carrier and region",
            "seasonal demand surge detection logs from traffic monitoring",
            "loyalty programme redemption patterns and expiry waste analysis",
        ],
    },
    "education": {
        "subtopics": [
            "student academic progression trajectories across secondary cycle",
            "standardised test score distributions by school and socioeconomic index",
            "teacher professional development hours and subject certification data",
            "school building infrastructure condition audit results",
            "online learning platform session duration and completion rates by course",
            "early school leaving risk scores from predictive model",
            "bilingual programme proficiency assessment outcomes",
            "university graduate employability survey six months post-graduation",
            "extracurricular participation rates and correlation with attendance",
            "special educational needs support allocation by local authority",
        ],
    },
    "manufacturing": {
        "subtopics": [
            "CNC machine vibration sensor logs for predictive maintenance",
            "production line defect rate by shift and workstation",
            "supply chain supplier on-time delivery and quality acceptance rates",
            "energy consumption per unit produced for ISO 50001 reporting",
            "product recall root cause classification from field returns",
            "tool wear measurement intervals and replacement cost tracking",
            "OEE availability, performance, and quality breakdowns per asset",
            "raw material commodity price exposure and hedging position data",
            "3D printing build plate utilisation and job success rate",
            "cleanroom particulate count monitoring for semiconductor fab",
        ],
    },
    "telecom": {
        "subtopics": [
            "mobile network KPI data including call drop rate and throughput per cell",
            "customer churn prediction features from CRM and billing system",
            "spectrum utilisation heatmap from drive-test measurements",
            "fixed broadband complaint resolution time by fault category",
            "roaming data consumption by country and visitor segment",
            "fibre network rollout progress and premises passed per NUTS-3",
            "IoT SIM card activation and deactivation events by vertical",
            "network congestion events correlated with major public gatherings",
            "over-the-top service quality monitoring from passive DPI probes",
            "number portability request volume and porting duration statistics",
        ],
    },
    "urban-mobility": {
        "subtopics": [
            "public bus GPS traces and schedule adherence at stop level",
            "metro passenger flow counts from gate validators by station and hour",
            "bike-sharing dock occupancy and rebalancing operation logs",
            "electric scooter trip origins, destinations, and battery level data",
            "traffic signal phase timing and queue length from loop detectors",
            "ride-hailing surge pricing activation zones and multipliers",
            "pedestrian footfall counters at major intersections",
            "parking occupancy sensor data for off-street car parks",
            "electric vehicle public charger utilisation and session energy by network",
            "multimodal journey planner query logs and itinerary selection rates",
        ],
    },
    "marine": {
        "subtopics": [
            "AIS vessel tracking with speed over ground and navigational status",
            "oceanographic CTD profiles of salinity and temperature",
            "fish stock assessment survey biomass estimates by species and cohort",
            "port container throughput and berth productivity statistics",
            "marine protected area surveillance camera detection events",
            "seabed habitat classification from multibeam bathymetric survey",
            "wave height and period from offshore buoy network",
            "aquaculture farm biomass production and mortality records",
            "oil spill satellite detection alerts and slick area estimates",
            "coral reef bleaching monitoring from in-situ temperature loggers",
        ],
    },
    "cybersecurity": {
        "subtopics": [
            "network intrusion detection system alert logs with MITRE ATT&CK tags",
            "vulnerability scanner findings with CVSS scores and remediation status",
            "phishing email campaign indicators of compromise and click rates",
            "dark web credential leak dataset with domain and breach source",
            "endpoint detection and response telemetry from SOC environment",
            "DNS query anomaly scores for domain generation algorithm detection",
            "web application firewall blocked request categorisation",
            "identity governance access review decisions and outlier flags",
            "ransomware incident timeline and recovery point objective metrics",
            "threat intelligence feed freshness and enrichment coverage report",
        ],
    },
    "hr": {
        "subtopics": [
            "employee turnover rate by department, tenure band, and exit reason",
            "time-to-fill and offer acceptance rate by job family and geography",
            "salary benchmarking data against external market percentiles",
            "engagement survey dimension scores and response rate by business unit",
            "training completion rate and learning hour allocation per quarter",
            "performance management rating distribution and calibration outcome",
            "absenteeism days and Bradford factor by role category",
            "diversity and inclusion representation metrics by seniority level",
            "internal mobility rate and promotion velocity by function",
            "workforce planning headcount forecast vs actual variance",
        ],
    },
    "energy-markets": {
        "subtopics": [
            "day-ahead electricity auction clearing prices and volumes by bidding zone",
            "intraday continuous trading price evolution for power exchange",
            "balancing mechanism activation volumes and marginal prices",
            "capacity market auction results and de-rated capacity by technology",
            "gas hub spot price index and storage injection/withdrawal flows",
            "renewable energy certificate issuance and cancellation by country",
            "interconnector cross-border flow and net transfer capacity data",
            "electricity distribution network outage events and restoration time",
            "power purchase agreement benchmark pricing by duration and technology",
            "carbon allowance futures settlement prices under EU ETS",
        ],
    },
}

# ---------------------------------------------------------------------------
# TARGET DOMAIN — 5 precisely-described assets; the suggested query targets
# these exclusively.  They live inside "smart-grid" but have a very specific
# sub-topic so the gate/filter can distinguish them from generic smart-grid
# noise assets.
# ---------------------------------------------------------------------------

TARGET_ASSETS = [
    {
        "id": "stress-smartgrid-dr-0001",
        "description": (
            "Demand Response Industrial Portugal — Registos horários de activações de "
            "programas de resposta à procura para consumidores industriais com potência "
            "contratada superior a 1 MVA. Inclui volumes de corte de carga (MW), "
            "preços de incentivo (€/MWh), e perfis de consumo medidos 30 minutos antes "
            "e depois de cada evento. Período 2020-2024. Formato Parquet. "
            "Industrial demand response activation records for large electricity consumers."
        ),
    },
    {
        "id": "stress-smartgrid-dr-0002",
        "description": (
            "Demand Response Industrial Spain — Hourly load curtailment events under the "
            "MIBEL interruptibility service for eligible industrial consumers. Contains "
            "contracted interruptible capacity (MW), actual shed load, activation notice "
            "period, and monthly settlement amounts. Covers aluminium smelters, cement "
            "plants, and chemical facilities. Period 2019-2024. CSV format."
        ),
    },
    {
        "id": "stress-smartgrid-dr-0003",
        "description": (
            "Industrial Demand Flexibility Aggregation Dataset — Aggregated flexibility "
            "bids submitted by industrial load aggregators to the TSO balancing market. "
            "Fields include site ID, available upward/downward flex (MW), response time "
            "commitment (minutes), bid price (€/MWh), and clearing outcome. Suitable for "
            "training demand response dispatch models. Period 2021-2024."
        ),
    },
    {
        "id": "stress-smartgrid-dr-0004",
        "description": (
            "Smart Meter Industrial Baseline Profiles — Fifteen-minute interval consumption "
            "baseline profiles for 340 industrial sites enrolled in demand response "
            "programmes. Baselines computed using CAISO-style day-matching methodology. "
            "Includes site metadata (sector, installed capacity, process type) and "
            "performance score per event. Period 2022-2024. Parquet format."
        ),
    },
    {
        "id": "stress-smartgrid-dr-0005",
        "description": (
            "Grid Stress Event Catalogue — Catalogue of high-price and frequency-deviation "
            "events that triggered industrial demand response calls. Each record includes "
            "event start/end UTC, triggering metric (price threshold or frequency nadir), "
            "total load shed achieved, and participation rate by industrial sector. "
            "Linked to the DR activation datasets dr-0001 through dr-0003. Period 2020-2024."
        ),
    },
]

TARGET_QUERY = (
    "I need datasets about industrial demand response programmes — "
    "specifically load curtailment activation records and flexibility bids "
    "from large electricity consumers or industrial sites."
)
TARGET_IDS = [a["id"] for a in TARGET_ASSETS]

SMART_GRID_SUBTOPICS = [
    "smart meter half-hourly consumption data for residential low-voltage feeders",
    "distribution transformer loading profiles and overload alert events",
    "EV charging session energy, power, and SOC data from public OCPP chargers",
    "battery energy storage system state-of-charge and dispatch schedules",
    "photovoltaic inverter output and grid injection records at secondary substation",
    "AMI head-end system meter tamper and outage detection event log",
    "distribution automation switching event records for fault location and isolation",
    "power quality measurements including THD and voltage unbalance at PCC",
    "load flow simulation results for LV network hosting capacity assessment",
    "asset health index scores for medium-voltage switchgear and cables",
]

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

CONTEXT = ["https://w3id.org/edc/connector/management/v0.0.1"]


def _session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Api-Key": api_key})
    return s


def _post(session: requests.Session, host: str, endpoint: str, body: Any) -> dict | None:
    url = f"{host}{endpoint}"
    try:
        resp = session.post(url, data=json.dumps(body), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 409:
            return {"conflict": True}
        print(f"  [WARN] POST {url}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [WARN] POST {url}: {e}", file=sys.stderr)
        return None


def _delete(session: requests.Session, host: str, endpoint: str) -> bool:
    url = f"{host}{endpoint}"
    try:
        resp = session.delete(url, timeout=30)
        return resp.status_code in (200, 204, 404)
    except Exception as e:
        print(f"  [WARN] DELETE {url}: {e}", file=sys.stderr)
        return False


def _list_all(session: requests.Session, host: str, endpoint: str) -> list:
    url = f"{host}{endpoint}"
    body = {"@context": CONTEXT, "offset": 0, "limit": 2000}
    try:
        resp = session.post(url, data=json.dumps(body), timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [WARN] LIST {url}: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _asset_payload(asset_id: str, description: str) -> dict:
    return {
        "@context": CONTEXT,
        "@id": asset_id,
        "@type": "Asset",
        "properties": {"description": description},
        "dataAddress": {
            "@type": "DataAddress",
            "type": "HttpData",
            "baseUrl": DUMMY_URL,
            "proxyPath": "true",
            "proxyQueryParams": "true",
        },
    }


def _contract_payload(asset_id: str) -> dict:
    return {
        "@context": CONTEXT,
        "@id": f"stress-contract-{asset_id}",
        "@type": "ContractDefinition",
        "accessPolicyId": ACCESS_POLICY_ID,
        "contractPolicyId": CONTRACT_POLICY_ID,
        "assetsSelector": {
            "@type": "Criterion",
            "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
            "operator": "=",
            "operandRight": asset_id,
        },
    }


# ---------------------------------------------------------------------------
# Asset generation
# ---------------------------------------------------------------------------

def _generate_assets() -> list[dict]:
    rng = random.Random(42)  # deterministic for reproducibility
    assets = []

    # --- noise assets: distribute evenly across all domains ---
    domain_list = list(DOMAINS.keys()) + ["smart-grid"]
    noise_count = TOTAL_ASSETS - len(TARGET_ASSETS)
    per_domain = noise_count // len(domain_list)
    remainder = noise_count % len(domain_list)

    counts = {d: per_domain for d in domain_list}
    for d in rng.sample(domain_list, remainder):
        counts[d] += 1

    seq = {d: 1 for d in domain_list}

    for domain in domain_list:
        if domain == "smart-grid":
            subtopics = SMART_GRID_SUBTOPICS
        else:
            subtopics = DOMAINS[domain]["subtopics"]

        for _ in range(counts[domain]):
            subtopic = rng.choice(subtopics)
            idx = seq[domain]
            seq[domain] += 1
            asset_id = f"{ASSET_PREFIX}{domain}-{idx:04d}"
            description = (
                f"{domain.replace('-', ' ').title()} dataset — {subtopic}. "
                f"Auto-generated stress-test asset #{idx}."
            )
            assets.append({"id": asset_id, "description": description})

    # --- target assets (appended last, not shuffled so manifest order is clear) ---
    for a in TARGET_ASSETS:
        assets.append({"id": a["id"], "description": a["description"]})

    rng.shuffle(assets)
    return assets


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def cmd_seed(host: str, api_key: str, workers: int) -> None:
    session = _session(api_key)
    assets = _generate_assets()

    print(f"\n=== Stress Seed ===")
    print(f"Host:    {host}")
    print(f"Assets:  {len(assets)}")
    print(f"Workers: {workers}\n")

    # -- Ensure policies exist --
    for policy_id, policy_body in [
        (
            ACCESS_POLICY_ID,
            {
                "@context": CONTEXT,
                "@type": "PolicyDefinition",
                "@id": ACCESS_POLICY_ID,
                "policy": {
                    "@type": "Set",
                    "permission": [
                        {
                            "action": "use",
                            "constraint": {
                                "leftOperand": "MembershipCredential",
                                "operator": "eq",
                                "rightOperand": "active",
                            },
                        }
                    ],
                },
            },
        ),
        (
            CONTRACT_POLICY_ID,
            {
                "@context": CONTEXT,
                "@type": "PolicyDefinition",
                "@id": CONTRACT_POLICY_ID,
                "policy": {
                    "@type": "Set",
                    "obligation": [
                        {
                            "action": "use",
                            "constraint": {
                                "leftOperand": "DataAccess.level",
                                "operator": "eq",
                                "rightOperand": "processing",
                            },
                        }
                    ],
                },
            },
        ),
    ]:
        r = _post(session, host, "/api/management/v3/policydefinitions", policy_body)
        if r and r.get("conflict"):
            print(f"  Policy {policy_id}: already exists (ok)")
        elif r:
            print(f"  Policy {policy_id}: created")
        else:
            print(f"  Policy {policy_id}: failed — aborting", file=sys.stderr)
            sys.exit(1)

    # -- Create assets (parallel) --
    print(f"\nCreating {len(assets)} assets...")
    t0 = time.time()
    ok = fail = 0

    def _create_asset(a):
        return _post(session, host, "/api/management/v3/assets", _asset_payload(a["id"], a["description"]))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_create_asset, a): a for a in assets}
        for i, fut in enumerate(as_completed(futures), 1):
            a = futures[fut]
            result = fut.result()
            if result is not None:
                ok += 1
            else:
                fail += 1
            if i % 100 == 0 or i == len(assets):
                elapsed = time.time() - t0
                print(f"  [{i}/{len(assets)}] ok={ok} fail={fail}  ({elapsed:.1f}s)")

    # -- Create contract definitions (parallel) --
    print(f"\nCreating {len(assets)} contract definitions...")
    t1 = time.time()
    cok = cfail = 0

    def _create_contract(a):
        return _post(session, host, "/api/management/v3/contractdefinitions", _contract_payload(a["id"]))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_create_contract, a): a for a in assets}
        for i, fut in enumerate(as_completed(futures), 1):
            a = futures[fut]
            result = fut.result()
            if result is not None:
                cok += 1
            else:
                cfail += 1
            if i % 100 == 0 or i == len(assets):
                elapsed = time.time() - t1
                print(f"  [{i}/{len(assets)}] ok={cok} fail={cfail}  ({elapsed:.1f}s)")

    # -- Save manifest --
    manifest = {
        "host": host,
        "asset_ids": [a["id"] for a in assets],
        "target_ids": TARGET_IDS,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest saved: {MANIFEST_PATH}")

    total = time.time() - t0
    print(f"\nDone in {total:.1f}s — assets: {ok}/{len(assets)}  contracts: {cok}/{len(assets)}")
    print()
    cmd_query()


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

def cmd_clean(host: str, api_key: str, workers: int) -> None:
    session = _session(api_key)

    # Load IDs from manifest if available, otherwise discover from EDC
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())
        asset_ids = manifest["asset_ids"]
        print(f"\n=== Stress Clean (from manifest: {len(asset_ids)} assets) ===")
    else:
        print("\n=== Stress Clean (discovering from EDC) ===")
        all_contracts = _list_all(session, host, "/api/management/v3/contractdefinitions/request")
        all_assets = _list_all(session, host, "/api/management/v3/assets/request")
        asset_ids = [a["@id"] for a in all_assets if a.get("@id", "").startswith(ASSET_PREFIX)]
        print(f"  Found {len(asset_ids)} stress assets")

    print(f"Host:    {host}")
    print(f"Workers: {workers}\n")

    # Delete contract defs first
    contract_ids = [f"stress-contract-{aid}" for aid in asset_ids]
    print(f"Deleting {len(contract_ids)} contract definitions...")
    t0 = time.time()
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_delete, session, host, f"/api/management/v3/contractdefinitions/{cid}"): cid for cid in contract_ids}
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                ok += 1
            if i % 100 == 0 or i == len(contract_ids):
                print(f"  [{i}/{len(contract_ids)}] ok={ok}  ({time.time()-t0:.1f}s)")

    # Delete assets
    print(f"\nDeleting {len(asset_ids)} assets...")
    t1 = time.time()
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_delete, session, host, f"/api/management/v3/assets/{aid}"): aid for aid in asset_ids}
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                ok += 1
            if i % 100 == 0 or i == len(asset_ids):
                print(f"  [{i}/{len(asset_ids)}] ok={ok}  ({time.time()-t1:.1f}s)")

    if MANIFEST_PATH.exists():
        MANIFEST_PATH.unlink()
        print(f"\nManifest removed: {MANIFEST_PATH}")

    print(f"\nDone in {time.time()-t0:.1f}s")


# ---------------------------------------------------------------------------
# Query hint
# ---------------------------------------------------------------------------

def cmd_query() -> None:
    print("=== Suggested Test Query ===")
    print()
    print(f'  "{TARGET_QUERY}"')
    print()
    print("Expected results (3-5 assets, all from stress-smartgrid-dr-*):")
    for aid in TARGET_IDS:
        print(f"  - {aid}")
    print()
    print("Why: these 5 assets share a very specific sub-topic (industrial demand")
    print("response) that does not appear in any of the 995 noise assets.")
    print("A well-tuned retrieval tool should return exactly these 5 and nothing else.")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["seed", "clean", "query"])
    parser.add_argument("--host", default=os.getenv("HOST_PROVIDER", "http://192.168.112.126/provider/cp"))
    parser.add_argument("--api-key", default=os.getenv("API_KEY", "password"))
    parser.add_argument("--workers", type=int, default=20, help="Parallel HTTP workers (default: 20)")
    args = parser.parse_args()

    if args.command == "seed":
        cmd_seed(args.host, args.api_key, args.workers)
    elif args.command == "clean":
        cmd_clean(args.host, args.api_key, args.workers)
    elif args.command == "query":
        cmd_query()


if __name__ == "__main__":
    main()
