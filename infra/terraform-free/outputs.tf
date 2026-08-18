output "public_ip" {
  description = "Public IP of the Argus instance"
  value       = aws_eip.argus.public_ip
}

output "api_url" {
  description = "Argus API base URL"
  value       = "http://${aws_eip.argus.public_ip}:8000"
}

output "health_url" {
  description = "Health check endpoint"
  value       = "http://${aws_eip.argus.public_ip}:8000/health"
}

output "ssh_key_file" {
  description = "Local path of the private key (write it there before ssh)"
  value       = "${path.module}/keys/argus-${var.environment}.pem"
}

output "ssh_command" {
  description = "SSH command to reach the instance"
  value       = "ssh -i ${path.module}/keys/argus-${var.environment}.pem ubuntu@${aws_eip.argus.public_ip}"
}
