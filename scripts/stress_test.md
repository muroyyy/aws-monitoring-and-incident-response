# Stress Test & Incident Simulation (Ubuntu / Amazon Linux)

> Use short, controlled bursts. Stop tests after you capture metrics/alerts.

## 0) Prep
Update packages:
```
sudo apt update -y || sudo yum update -y
```

Install CloudWatch Agent (if not yet) to emit mem/disk metrics:
- Ubuntu (deb): https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
- Amazon Linux (rpm): https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm

1) CPU Spike (2 minutes)

Install stress:
```
# Ubuntu/Debian
sudo apt install -y stress
# Amazon Linux
sudo yum install -y stress
```

Run spike (use <= number of vCPUs):
```
stress --cpu 4 --timeout 120
```

Alternative (quick & dirty):
```
yes > /dev/null & yes > /dev/null & yes > /dev/null & yes > /dev/null &
# Stop:
killall yes || true
```

2) Memory Pressure

Allocate memory with stress:
```
# Allocate ~1GB across 2 workers for 2 minutes
stress --vm 2 --vm-bytes 512M --timeout 120
```

3) Disk Usage / Fill

Create a temporary large file (adjust size to your disk):
```
# 1 GB file
fallocate -l 1G /tmp/ir_testfile || dd if=/dev/zero of=/tmp/ir_testfile bs=1M count=1024
```

Cleanup:
```
rm -f /tmp/ir_testfile
```

4) Disk I/O Pressure (optional)

```
dd if=/dev/zero of=/tmp/io_blast bs=4M count=512 oflag=direct
rm -f /tmp/io_blast
```

5) Network Burst (optional, requires iperf3 server somewhere)

```
sudo apt install -y iperf3 || sudo yum install -y iperf3
iperf3 -c <IP_OF_SERVER> -t 
```

6) Verify Metrics & Alerts

- CloudWatch → Metrics:
    - AWS/EC2 → CPUUtilization
    - CWAgent → mem_used_percent, disk_used_percent

- Watch your Telegram channel for alerts from the detector Lambda.
- If SNAPSHOT_ON_ALERT=true, check EC2 → Snapshots.

7) Safety

- Keep tests short (--timeout) to avoid unintended costs.
- Close any background loops: killall yes and cleanup temp files.