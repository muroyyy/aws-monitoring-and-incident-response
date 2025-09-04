output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.ir_ec2.id
}

output "instance_private_ip" {
  description = "EC2 private IP"
  value       = aws_instance.ir_ec2.private_ip
}

output "instance_public_ip" {
  description = "EC2 public IP (if subnet/assignments allow)"
  value       = aws_instance.ir_ec2.public_ip
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.ec2_no_inbound.id
}

output "iam_instance_profile" {
  description = "IAM instance profile name"
  value       = aws_iam_instance_profile.ec2_profile.name
}
