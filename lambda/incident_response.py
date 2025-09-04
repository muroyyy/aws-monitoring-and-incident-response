"""
Lambda: Autonomous Incident Detector (alarm-less) + Telegram alerts
Optional: take EBS snapshots and start a Step Functions playbook.

ENV VARS (set in Lambda console or IaC):
- INSTANCE_IDS           = i-0123abcd,i-0456efgh         # comma-separated
- CPU_HIGH               = 80                            # %
- MEM_HIGH               = 85                            # %
- DISK_HIGH              = 85                            # %
- COOLDOWN_SEC           = 900                           # suppress duplicate alerts within N seconds per instance
- TELEGRAM_BOT_TOKEN     = <bot token>
- TELEGRAM_CHANNEL_ID    = <chat id>
- STATE_TABLE            = <DynamoDB table name>         # optional (for dedup). If absent, dedup is disabled.
- SNAPSHOT_ON_ALERT      = true|false                    # optional (default false)
- PLAYBOOK_ARN           = arn:aws:states:...:stateMachine/IncidentPlaybook  # optional
- REGION                 = ap-southeast-1               # optional; falls back to Lambda region
"""

import os
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config

REGION = os.environ.get("REGION") or os.environ.get("AWS_REGION") or "us-east-1"
boto_cfg = Config(region_name=REGION)

CW   = boto3.client("cloudwatch", config=boto_cfg)
EC2  = boto3.client("ec2", config=boto_cfg)
SFN  = boto3.client("stepfunctions", config=boto_cfg)

# Optional clients (created lazily)
DDB_TABLE_NAME = os.environ.get("STATE_TABLE")
DDB  = boto3.resource("dynamodb", config=boto_cfg).Table(DDB_TABLE_NAME) if DDB_TABLE_NAME else None

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.environ.get("TELEGRAM_CHANNEL_ID")

CPU_HIGH  = float(os.environ.get("CPU_HIGH", "80"))
MEM_HIGH  = float(os.environ.get("MEM_HIGH", "85"))
DISK_HIGH = float(os.environ.get("DISK_HIGH", "85"))
COOLDOWN  = int(os.environ.get("COOLDOWN_SEC", "900"))

SNAPSHOT_ON_ALERT = os.environ.get("SNAPSHOT_ON_ALERT", "false").lower() == "true"
PLAYBOOK_ARN = os.environ.get("PLAYBOOK_ARN")

def _telegram(text: str):
    if not (BOT_TOKEN and CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()

def _avg_stats(namespace: str, metric: str, dim: dict, minutes=5, stat="Average"):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    resp = CW.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric,
        Dimensions=[dim],
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=[stat],
    )
    points = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
    if not points:
        return None
    vals = [p[stat] for p in points if stat in p]
    return sum(vals) / len(vals) if vals else None

def _dedup_ok(iid: str) -> bool:
    """Return True if we are allowed to alert (not within cooldown)."""
    if not DDB:
        return True
    item = DDB.get_item(Key={"pk": iid}).get("Item")
    last_ts = item.get("last_ts") if item else 0
    if time.time() - last_ts < COOLDOWN:
        return False
    DDB.put_item(Item={"pk": iid, "last_ts": int(time.time())})
    return True

def _snapshots_for_instance(iid: str):
    """Create EBS snapshots for all attached volumes of the instance."""
    desc = EC2.describe_instances(InstanceIds=[iid])
    vol_ids = []
    for r in desc.get("Reservations", []):
        for inst in r.get("Instances", []):
            for m in inst.get("BlockDeviceMappings", []):
                ebs = m.get("Ebs")
                if ebs and ebs.get("VolumeId"):
                    vol_ids.append(ebs["VolumeId"])
    snaps = []
    for vid in vol_ids:
        snap = EC2.create_snapshot(
            VolumeId=vid,
            Description=f"IR snapshot for {iid} @ {datetime.utcnow().isoformat()}Z"
        )
        snaps.append(snap["SnapshotId"])
        EC2.create_tags(
            Resources=[snap["SnapshotId"]],
            Tags=[
                {"Key": "IR", "Value": "true"},
                {"Key": "InstanceId", "Value": iid},
            ],
        )
    return snaps

def lambda_handler(event, context):
    instances_raw = os.environ.get("INSTANCE_IDS", "").strip()
    if not instances_raw:
        _telegram("⚠️ IR Detector: No INSTANCE_IDS configured.")
        return {"error": "no instances"}
    instance_ids = [s.strip() for s in instances_raw.split(",") if s.strip()]

    incidents = []
    for iid in instance_ids:
        cpu  = _avg_stats("AWS/EC2", "CPUUtilization", {"Name":"InstanceId","Value":iid}, minutes=5)
        mem  = _avg_stats("CWAgent", "mem_used_percent", {"Name":"InstanceId","Value":iid}, minutes=5)
        disk = _avg_stats("CWAgent", "disk_used_percent", {"Name":"InstanceId","Value":iid}, minutes=5)

        signals = []
        if cpu is not None and cpu > CPU_HIGH:   signals.append(f"CPU {cpu:.1f}% > {CPU_HIGH}%")
        if mem is not None and mem > MEM_HIGH:   signals.append(f"MEM {mem:.1f}% > {MEM_HIGH}%")
        if disk is not None and disk > DISK_HIGH:signals.append(f"DISK {disk:.1f}% > {DISK_HIGH}%")

        if not signals:
            continue

        if not _dedup_ok(iid):
            # Suppressed due to cooldown
            continue

        incident_id = f"{iid}-{int(time.time())}"
        msg = (
            f"🚨 Incident detected\n"
            f"Instance: {iid}\n"
            f"Signals: {', '.join(signals)}\n"
            f"IncidentId: {incident_id}"
        )
        _telegram(msg)

        # Optional: take snapshots for forensics
        snaps = []
        if SNAPSHOT_ON_ALERT:
            try:
                snaps = _snapshots_for_instance(iid)
                _telegram(f"🧩 Snapshots taken for {iid}: {', '.join(snaps) if snaps else 'none'}")
            except Exception as e:
                _telegram(f"⚠️ Snapshot error for {iid}: {e}")

        # Optional: start a Step Functions playbook
        if PLAYBOOK_ARN:
            try:
                SFN.start_execution(
                    stateMachineArn=PLAYBOOK_ARN,
                    input=json.dumps({
                        "incidentId": incident_id,
                        "instanceId": iid,
                        "signals": signals,
                        "snapshots": snaps
                    })
                )
                _telegram("▶️ Playbook started.")
            except Exception as e:
                _telegram(f"⚠️ Failed to start playbook: {e}")

        incidents.append({"instance": iid, "signals": signals, "snapshots": snaps})

    return {"incidents": incidents}
