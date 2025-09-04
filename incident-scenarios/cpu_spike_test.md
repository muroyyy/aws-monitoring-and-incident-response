# 🖥️ CPU Spike Incident Simulation via SSM (no SSH)

This scenario uses **AWS Systems Manager (SSM) Session Manager & Run Command** to trigger a controlled CPU spike on an EC2 instance with an SSM-enabled IAM role.

---

## ✅ Prereqs
- Instance has:
  - **IAM instance profile** with `AmazonSSMManagedInstanceCore` (or equivalent least-privilege).
  - **SSM Agent** installed (preinstalled on Amazon Linux 2/Ubuntu 22.04 AMIs).
  - Network egress to SSM endpoints (public internet or VPC endpoints for `ssm`, `ec2messages`, `ssmmessages`).
- **Detector Lambda** deployed & EventBridge scheduled (`rate(5 minutes)`).
- **CloudWatch Agent** installed if you want memory/disk metrics (optional but recommended).

---

## 🚀 Option A — Interactive shell via Session Manager (Console)
1. EC2 > **Instances** > select instance > **Connect** > **Session Manager** > **Connect**.
2. Run:
   ```
   sudo yum -y install stress || (sudo apt update -y && sudo apt -y install stress)
   stress --cpu 4 --timeout 120
   ```
3. (Alt quick load)

```
yes > /dev/null & yes > /dev/null & yes > /dev/null & yes > /dev/null &
# stop
killall yes || true
```

⚡ Option B — Non-interactive via SSM Run Command (Console)
1. Systems Manager > Run Command > Run command.
2. Document: AWS-RunShellScript.
3. Targets: select your instance.
4. Command:
```
sudo yum -y install stress || (sudo apt update -y && sudo apt -y install stress)
stress --cpu 4 --timeout 120
```
5. Run. Watch command output/logs in the same page.

🧰 Option C — Non-interactive via AWS CLI
Replace the placeholders before running.

```
INSTANCE_ID=i-0123456789abcdef0
REGION=ap-southeast-1

aws ssm send-command \
  --region $REGION \
  --document-name "AWS-RunShellScript" \
  --comment "CPU spike test for IR pipeline" \
  --targets "Key=instanceids,Values=$INSTANCE_ID" \
  --parameters '{
    "commands":[
      "set -euxo pipefail",
      "sudo yum -y install stress || (sudo apt update -y && sudo apt -y install stress)",
      "stress --cpu 4 --timeout 120"
    ]
  }' \
  --output-s3-bucket-name "" \
  --output text
```

🔍 Expected Results
- CloudWatch: AWS/EC2 → CPUUtilization spikes above your CPU_HIGH threshold.
- Detector Lambda (runs on next EventBridge tick):
    - Evaluates metrics and sends Telegram alert.
    - (Optional) Creates EBS snapshots.
    - (Optional) Kicks off Step Functions playbook.

Sample Telegram:
```
🚨 Incident detected
Instance: i-0123456789abcdef0
Signals: CPU 95.2% > 80%
IncidentId: i-0123456789abcdef0-1700000000
```

📸 Artifacts to Save (into /docs)
- CloudWatch CPU graph screenshot (cloudwatch-metrics.png).
- Telegram alert screenshot (telegram-alert.png).
- EC2 Snapshots view (if enabled) (snapshots.png).

🧹 Cleanup
If you used yes processes:

```
killall yes || true
```